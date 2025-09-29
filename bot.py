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

def fetch_release_date_from_store_api(app_id: str) -> str:
    """
    ดึงวันวางจำหน่ายจาก Steam Store API และแปลงเป็นภาษาไทยเต็ม
    """
    url = f"{STEAM_APP_DETAILS_URL}{app_id}&cc=th&l=th"

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

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data and data.get(app_id, {}).get('success') is True:
            raw_date = data[app_id].get('data', {}).get('release_date', {}).get('date', 'ไม่ระบุ')
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

        return 'ไม่ระบุ'

    except requests.RequestException:
        return 'ไม่ระบุ'


def get_steam_info(app_id):
    release_date_thai = fetch_release_date_from_store_api(app_id)
    
    try:
        url = f"{STEAMCMD_API_URL}{app_id}"
        response = requests.get(url, timeout=7)
        response.raise_for_status()
        data = response.json()
        if data and data.get('status') == 'success' and app_id in data['data']:
            app_data = data['data'][app_id]
            common = app_data.get('common', {})
            extended = app_data.get('extended', {})
            
            name = common.get('name', 'ไม่พบแอป')
            header_image_hash = common.get('header_image', {}).get('english')
            header_image = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/{header_image_hash}" if header_image_hash else None
            
            dlc_list_str = extended.get('listofdlc', '')
            dlc_items = [item for item in dlc_list_str.split(',') if item.strip()]
            dlc_count = len(dlc_items)

            return {
                'name': name,
                'image': header_image,
                'dlc_count': dlc_count,
                'release_date': release_date_thai,
            }
        return None
    except requests.RequestException:
        return None

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

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    app_id = extract_app_id(message.content)
    if app_id:
        await message.channel.typing()
        steam_data = get_steam_info(app_id)
        file_url_200 = check_file_status(app_id) 
        
        embed = discord.Embed(
            title=f"🔎 ข้อมูล Steam App ID: {app_id}",
            color=0x1b2838
        )
        
        if steam_data:
            embed.add_field(name="ชื่อแอป", value=steam_data['name'], inline=False)
            embed.add_field(name="DLCs ทั้งหมด", value=f"พบ **{steam_data['dlc_count']}** รายการ", inline=True)
            embed.add_field(name="วันวางจำหน่าย", value=steam_data['release_date'], inline=False)
            embed.add_field(
                name="Links", 
                value=f"[Steam Store](https://store.steampowered.com/app/{app_id}/) | [SteamDB](https://steamdb.info/app/{app_id}/)", 
                inline=False
            )
            
            if steam_data['image']:
                embed.set_image(url=steam_data['image'])
        else:
            embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
            
        if file_url_200:
            embed.add_field(
                name=f"📦 สถานะ: ✅ [**พร้อมดาวน์โหลด↗**]({file_url_200})", 
                value="", 
                inline=False
            )
        else:
            embed.add_field(
                name="📦 สถานะ: ❌ ไม่พบไฟล์", 
                value="", 
                inline=False
            )
        
        await message.channel.send(embed=embed)

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
