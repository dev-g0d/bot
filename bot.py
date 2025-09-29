import discord
from discord.ext import commands
import requests
import re
import os
import threading
from flask import Flask 
import json

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
MELLY_BASE_URL = "https://mellyiscoolaf.pythonanywhere.com/" 
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
            
            name = common.get('name', 'N/A')
            header_image_hash = common.get('header_image', {}).get('english')
            header_image = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/{header_image_hash}" if header_image_hash else None
            
            dlc_list_str = extended.get('listofdlc', '')
            dlc_items = [item for item in dlc_list_str.split(',') if item.strip()]
            dlc_count = len(dlc_items)
            
            return {
                'name': name,
                'image': header_image,
                'dlc_count': dlc_count,
            }
        return None
    except requests.RequestException as e:
        print(f"Error fetching SteamCMD info for {app_id}: {e}")
        return None

def check_file_status(app_id):
    # STEP 1: เช็ค Melly
    melly_check_url = f"{MELLY_BASE_URL}{app_id}"
    try:
        melly_response = requests.get(melly_check_url, allow_redirects=False, timeout=7)
        if melly_response.status_code != 200:
            return None
    except requests.exceptions.RequestException:
        return None

    # STEP 2: ขอ URL จาก Devg0d
    devgod_request_url = f"{DEVGOD_BASE_URL}{app_id}"
    try:
        devgod_response = requests.get(devgod_request_url, allow_redirects=True, timeout=10)
        # เอา URL สุดท้ายเลย ไม่ต้องเช็ค status
        return devgod_response.url
    except requests.exceptions.RequestException:
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
            embed.add_field(name="ชื่อเกม", value=steam_data['name'], inline=False)
            embed.add_field(name="DLCs (จาก SteamCMD)", value=f"พบ **{steam_data['dlc_count']}** รายการ", inline=True)
            embed.add_field(name="ลิงก์ Steam Store", value=f"[คลิกที่นี่](https://store.steampowered.com/app/{app_id}/)", inline=True)
            if steam_data['image']:
                embed.set_thumbnail(url=steam_data['image'])
        else:
            embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
            
        if file_url_200:
            embed.add_field(
                name="🔗 สถานะและลิงก์ดาวน์โหลด", 
                value=f"สถานะ: **✅ พร้อมดาวน์โหลด**\n[**ดาวน์โหลด↗**]({file_url_200})", 
                inline=False
            )
        else:
            embed.add_field(
                name="🔗 สถานะและลิงก์ดาวน์โหลด", 
                value="สถานะ: **❌ ไม่พบไฟล์/ลิงก์ไม่พร้อม**", 
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
