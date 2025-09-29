import discord
from discord.ext import commands
import requests
import re
import os
import threading
from flask import Flask 
import json
import time
import datetime # เพิ่ม: สำหรับจัดการวันที่
import locale   # เพิ่ม: สำหรับตั้งค่าภาษาไทย

# --- ตั้งค่า Locale เป็นภาษาไทย (สำคัญสำหรับการแสดงชื่อเดือน) ---
# การตั้งค่านี้อาจแตกต่างกันไปตามระบบปฏิบัติการ (Windows, Linux, Mac)
try:
    locale.setlocale(locale.LC_ALL, 'th_TH.utf8')
except locale.Error:
    try:
        # ลองใช้โค้ดสำหรับระบบอื่น ๆ หรือ environments ที่รองรับ
        locale.setlocale(locale.LC_ALL, 'th_TH')
    except locale.Error:
        # หากไม่สามารถตั้งค่าภาษาไทยได้จริง ๆ ให้ใช้ภาษาอังกฤษเป็นค่า fallback
        print("Warning: Could not set Thai locale. Dates will be in English/Default format.")
        pass


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

def get_steam_info(app_id):
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

            # ดึงข้อมูลวันวางจำหน่ายเป็น string ภาษาอังกฤษ
            release_date_str = common.get('release_date', {}).get('english', 'ไม่ระบุ')
            
            release_date_thai = 'ไม่ระบุ'
            if release_date_str != 'ไม่ระบุ':
                try:
                    # พยายามแปลงจากรูปแบบ 'Month DD, YYYY'
                    release_date_obj = datetime.datetime.strptime(release_date_str, '%b %d, %Y')
                    # จัดรูปแบบวันที่เป็นภาษาไทย: วันที่(ไม่มี 0 นำหน้า) เดือนเต็ม ปี ค.ศ.
                    release_date_thai = release_date_obj.strftime('%#d %B %Y')
                except ValueError:
                    # ถ้าแปลงไม่ได้ แสดงว่าเป็นวันที่ที่ Steam ระบุเป็นข้อความ (เช่น 'TBA' หรือ 'Q1 2025')
                    release_date_thai = release_date_str 
            
            return {
                'name': name,
                'image': header_image,
                'dlc_count': dlc_count,
                'release_date': release_date_thai, # ใช้ค่าวันที่ภาษาไทย
            }
        return None
    except requests.RequestException as e:
        print(f"Error fetching SteamCMD info for {app_id}: {e}")
        return None

def check_file_status(app_id: str) -> str | None:
    """
    ส่ง request ไปยัง devg0d.pythonanywhere.com/app_request/{appid}
    ตาม redirect จนถึงปลายทาง
    ถ้า final response = 200 และมี content-disposition -> return URL
    ถ้าไม่ใช่ -> return None
    """
    url = f"{DEVGOD_BASE_URL}{app_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        final_url = response.url   # URL ปลายทางที่ redirect ไปถึง

        if response.status_code == 200 and "content-disposition" in response.headers:
            return final_url  # คืนลิงก์ไฟล์จริง
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
            
            # เพิ่ม: วันวางจำหน่ายภาษาไทย
            embed.add_field(name="วันวางจำหน่าย", value=steam_data['release_date'], inline=False) 
            
            embed.add_field(name="DLCs ทั้งหมด", value=f"พบ **{steam_data['dlc_count']}** รายการ", inline=True)
            
            # แก้ไข: เปลี่ยนเป็น Links และเพิ่ม SteamDB (inline=False)
            embed.add_field(name="Links", 
                            value=f"[Steam Store](https://store.steampowered.com/app/{app_id}/) | [SteamDB](https://steamdb.info/app/{app_id}/)", 
                            inline=False)
            
            if steam_data['image']:
                embed.set_thumbnail(url=steam_data['image'])
        else:
            embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
            
        if file_url_200:
            embed.add_field(
                name="📦 สถานะ: ✅ พร้อมดาวน์โหลด", 
                value=f"[**ดาวน์โหลด↗**]({file_url_200})", 
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
