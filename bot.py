import discord
from discord.ext import commands
import requests
import re
import os
import threading
from flask import Flask 
import datetime

# --- 1. Flask Keep-Alive Setup ---
web_app = Flask('') 

@web_app.route('/')
def home():
    return "Discord Bot is running and ready to serve!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    t = threading.Thread(target=run_web_server)
    t.start()
    
# --- 2. Configuration & API Endpoints ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") 
ALLOWED_CHANNEL_ID = 1098314625646329966  
DEVGOD_BASE_URL = "https://devg0d.pythonanywhere.com/app_request/"
STEAMCMD_API_URL = "https://api.steamcmd.net/v1/info/"
STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails?appids="

# Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- 3. Helper Functions ---
def extract_app_id(message_content):
    if message_content.isdigit():
        return message_content
    match = re.search(r'(?:steamdb\.info\/app\/|store\.steampowered\.com\/app\/)(\d+)', message_content)
    if match:
        return match.group(1)
    return None

def fetch_release_date_from_store_data(store_data: dict) -> str:
    """
    ดึงวันวางจำหน่ายจากข้อมูล Steam Store API และแปลงเป็นภาษาไทยเต็ม
    """
    en_to_th = {
        "Jan": "มกราคม", "Feb": "กุมภาพันธ์", "Mar": "มีนาคม", "Apr": "เมษายน",
        "May": "พฤษภาคม", "Jun": "มิถุนายน", "Jul": "กรกฎาคม", "Aug": "สิงหาคม",
        "Sep": "กันยายน", "Oct": "ตุลาคม", "Nov": "พฤศจิกายน", "Dec": "ธันวาคม"
    }

    th_short_to_full = {
        "ม.ค.": "มกราคม", "ก.พ.": "กุมภาพันธ์", "มี.ค.": "มีนาคม", "เม.ย.": "เมษายน",
        "พ.ค.": "พฤษภาคม", "มิ.ย.": "มิถุนายน", "ก.ค.": "กรกฎาคม", "ส.ค.": "สิงหาคม",
        "ก.ย.": "กันยายน", "ต.ค.": "ตุลาคม", "พ.ย.": "พฤศจิกายน", "ธ.ค.": "ธันวาคม"
    }

    raw_date = store_data.get('release_date', {}).get('date', 'ไม่ระบุ')
    if raw_date == 'ไม่ระบุ':
        return 'ไม่ระบุ'

    # กรณีภาษาไทยย่อ เช่น "28 เม.ย. 2017"
    for short, full in th_short_to_full.items():
        if short in raw_date:
            return raw_date.replace(short, full)

    # กรณีภาษาอังกฤษ เช่น "Apr 27, 2017"
    try:
        dt = datetime.datetime.strptime(raw_date, "%b %d, %Y")
        return f"{dt.day} {en_to_th[dt.strftime('%b')]} {dt.year}"
    except ValueError:
        pass

    # กรณีอื่น ๆ ส่งกลับไปตรง ๆ
    return raw_date

def get_steam_info(app_id):
    # --- ดึงข้อมูลจาก Steam Store API ก่อน (รวม release_date, name, dlc, header_image, drm_notice) ---
    header_image_store = None
    name_store = None
    dlc_count_store = 0
    release_date_thai = 'ไม่ระบุ'
    store_success = False
    has_denuvo = False
    drm_notice = ""

    try:
        store_url = f"{STEAM_APP_DETAILS_URL}{app_id}&cc=th&l=th"
        store_resp = requests.get(store_url, timeout=5)
        store_resp.raise_for_status()
        store_data = store_resp.json()
        if store_data and store_data.get(app_id, {}).get("success") is True:
            store_info = store_data[app_id].get("data", {})
            store_success = True
            name_store = store_info.get("name", 'ไม่พบแอป')
            header_image_store = store_info.get("header_image")
            dlc_list = store_info.get("dlc", [])
            dlc_count_store = len(dlc_list)
            release_date_thai = fetch_release_date_from_store_data(store_info)
            drm_notice = store_info.get("drm_notice", "")
            has_denuvo = "denuvo" in drm_notice.lower()
    except requests.RequestException as e:
        print(f"Steam Store fetch error: {e}")

    # --- ดึงข้อมูลจาก SteamCMD API (สำหรับ DLC prioritize, name fallback, header fallback) ---
    header_image_hash = None
    dlc_count_cmd = 0
    name_cmd = 'ไม่พบแอป'
    cmd_success = False
    try:
        url = f"{STEAMCMD_API_URL}{app_id}"
        response = requests.get(url, timeout=7)
        response.raise_for_status()
        data = response.json()
        if data and data.get('status') == 'success' and app_id in data['data']:
            app_data = data['data'][app_id]
            common = app_data.get('common', {})
            extended = app_data.get('extended', {})
            cmd_success = True

            name_cmd = common.get('name', 'ไม่พบแอป')
            header_image_hash = common.get('header_image', {}).get('english')
            dlc_list_str = extended.get('listofdlc', '')
            dlc_items = [item for item in dlc_list_str.split(',') if item.strip()]
            dlc_count_cmd = len(dlc_items)
    except requests.RequestException as e:
        print(f"SteamCMD fetch error: {e}")

    # --- รวมข้อมูล: prioritize Store สำหรับส่วนใหญ่ แต่ DLC prioritize CMD ถ้ามี ---
    name = name_store if store_success else name_cmd
    dlc_count = dlc_count_cmd if cmd_success and dlc_count_cmd > 0 else dlc_count_store
    header_image = header_image_store or (f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/{header_image_hash}" if header_image_hash else None)

    if not name:
        return None

    return {
        'name': name,
        'image': header_image,
        'dlc_count': dlc_count,
        'release_date': release_date_thai,
        'has_denuvo': has_denuvo,
    }
        
def check_file_status(app_id: str) -> str | None:
    url = f"{DEVGOD_BASE_URL}{app_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        final_url = response.url
        if response.status_code == 200 and "content-disposition" in response.headers:
            return final_url
    except requests.RequestException:
        return None
    return None

# --- 4. Discord Events ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('Bot is ready and running!')
    await bot.change_presence(activity=discord.Game(name="24/7 for Manifest"))  # Set bot status

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id != ALLOWED_CHANNEL_ID:
        return  # Ignore all activity if not in allowed channel

    app_id = extract_app_id(message.content)
    if app_id:
        steam_data = get_steam_info(app_id)
        file_url_200 = check_file_status(app_id) 
        
        embed = discord.Embed(
            title=f"🔎 ข้อมูล Steam App ID: {app_id}",
            color=0x00FF00 if file_url_200 else 0xFF0000
        )
        
        if steam_data:
            embed.add_field(name="ชื่อแอป", value=steam_data['name'], inline=False)
            embed.add_field(name="DLCs ทั้งหมด", value=f"พบ **{steam_data['dlc_count']}** รายการ", inline=True)
            embed.add_field(name="วันวางจำหน่าย", value=steam_data['release_date'], inline=False)
            links_value = f"[Steam Store](https://store.steampowered.com/app/{app_id}/) | [SteamDB](https://steamdb.info/app/{app_id}/)"
            if steam_data['has_denuvo']:
                links_value += "\n:warning: ตรวจพบการป้องกัน Denuvo"
            embed.add_field(
                name="Links", 
                value=links_value, 
                inline=False
            )
            
            if steam_data['image']:
                embed.set_image(url=steam_data['image'])
        else:
            embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
            
        if file_url_200:
            embed.add_field(
                name="", 
                value=f"**📦 สถานะ:** ✅ [**พร้อมดาวน์โหลด↗**]({file_url_200})", 
                inline=False
            )
        else:
            embed.add_field(
                name="📦 สถานะ: ❌ ไม่พบไฟล์", 
                value="", 
                inline=False
            )
        
        await message.reply(embed=embed)

# --- 5. Main Execution ---
if __name__ == '__main__':
    keep_alive() 
    try:
        if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            print("FATAL ERROR: Please set the DISCORD_BOT_TOKEN environment variable or change the default value.")
        else:
            bot.run(DISCORD_BOT_TOKEN)
    except discord.errors.LoginFailure:
        print("FATAL ERROR: Invalid Discord Bot Token. Please check your token.")
    except Exception as e:
        print(f"An error occurred while running the bot: {e}")
