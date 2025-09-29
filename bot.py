import discord
from discord.ext import commands
import requests
import re
import os
import threading
from flask import Flask 
import json # เพิ่มการ import json สำหรับการจัดการ response

# --- 1. Flask Keep-Alive Setup ---
# สร้าง Flask App เพื่อตอบสนองต่อ Health Check ของ Render
web_app = Flask('') 

@web_app.route('/')
def home():
    """Endpoint สำหรับ Health Check ของ Render"""
    return "Discord Bot is running and ready to serve!"

def run_web_server():
    """รัน Web Server ใน Thread แยก โดยใช้ use_reloader=False เพื่อป้องกัน KeyError"""
    port = int(os.environ.get("PORT", 8080))
    # สำคัญ: ต้องใส่ use_reloader=False เพื่อป้องกันการ Fork Process ที่ทำให้เกิด KeyError
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    """เริ่ม Thread สำหรับ Web Server เพื่อป้องกันไม่ให้ Render ปิด Worker"""
    t = threading.Thread(target=run_web_server)
    t.start()
    
# --- 2. Configuration & API Endpoints ---
# ดึง Discord Token จาก Environment Variables บน Render
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") 

# กำหนด ID ห้องที่อนุญาตให้บอททำงาน
# **สำคัญ:** เปลี่ยนเลขนี้เป็น ID ช่องจริงของคุณ
ALLOWED_CHANNEL_ID = 1098314625646329966  

# URL สำหรับตรวจสอบสถานะ (Gatekeeper)
MELLY_BASE_URL = "https://mellyiscoolaf.pythonanywhere.com/" 

# URL สำหรับดึง URL ปลายทาง (ตามที่คุณต้องการให้ส่งลิงก์จาก Request นี้)
DEVGOD_BASE_URL = "https://devg0d.pythonanywhere.com/app_request/"

# ใช้ API นี้แทน Steam Store เพื่อข้อมูลที่แม่นยำกว่า (รวม DLCs)
STEAMCMD_API_URL = "https://api.steamcmd.net/v1/info/"

# ตั้งค่า Intents ที่จำเป็น
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True # ต้องเปิดใน Developer Portal
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- 3. Helper Functions ---
def extract_app_id(message_content):
    """ดึง App ID จากข้อความที่ป้อน (เลขล้วน หรือ URL Steam/SteamDB)"""
    if message_content.isdigit():
        return message_content
    # Regex เพื่อจับเลข App ID จาก URL ทั้ง SteamDB และ Steam Store
    match = re.search(r'(?:steamdb\.info\/app\/|store\.steampowered\.com\/app\/)(\d+)', message_content)
    if match:
        return match.group(1)
    return None

def get_steam_info(app_id):
    """ดึงข้อมูลเกมและนับ DLCs จาก SteamCMD API"""
    try:
        url = f"{STEAMCMD_API_URL}{app_id}"
        response = requests.get(url, timeout=7)
        response.raise_for_status()
        data = response.json()
        
        # ตรวจสอบว่ามีข้อมูลและอยู่ในสถานะ 'success' หรือไม่
        if data and data.get('status') == 'success' and app_id in data['data']:
            app_data = data['data'][app_id]
            common = app_data.get('common', {})
            extended = app_data.get('extended', {})
            
            name = common.get('name', 'N/A')
            # ดึง Header Image (ต้องแปลงให้เป็น URL ที่ใช้งานได้)
            header_image_hash = common.get('header_image', {}).get('english')
            # กำหนด URL ภาพ Header ของ Steam 
            header_image = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/{header_image_hash}" if header_image_hash else None
            
            # ตรรกะการนับ DLCs 
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
    """
    ขั้นตอนการตรวจสอบสถานะและดึง URL ปลายทาง:
    1. ตรวจสอบสถานะ 200 OK ที่ mellyiscoolaf/m/{app_id} (Gatekeeper)
    2. ถ้า Gatekeeper ผ่าน (ได้ 200) จึงจะทำการ Request ไปที่ devg0d เพื่อดึง URL ปลายทาง
    3. คืนค่า URL ปลายทางสุดท้ายจาก devg0d หากสถานะปลายทางเป็น 200 OK
    """
    
    # --- 1. ตรวจสอบ Melly (Gatekeeper) ---
    melly_check_url = f"{MELLY_BASE_URL}{app_id}"
    try:
        # ใช้ requests.head เพื่อตรวจสอบสถานะอย่างรวดเร็ว
        melly_response = requests.head(melly_check_url, allow_redirects=True, timeout=5)
        
        if melly_response.status_code != 200:
            print(f"Melly check failed for {app_id}. Status: {melly_response.status_code}")
            return None # Melly check ไม่ผ่าน ไม่ต้องทำต่อ
            
    except requests.exceptions.RequestException as e:
        print(f"Error checking Melly status for {app_id}: {e}")
        return None 
    
    # --- 2. Gatekeeper ผ่านแล้ว -> ทำการ Request Devg0d เพื่อดึง URL ปลายทาง ---
    devgod_request_url = f"{DEVGOD_BASE_URL}{app_id}"
    
    try:
        # ใช้ requests.get เพื่อติดตาม Redirect ทั้งหมดไปจนถึง URL ปลายทางสุดท้าย
        devgod_response = requests.get(devgod_request_url, allow_redirects=True, timeout=10)
        
        # --- 3. ตรวจสอบสถานะปลายทางของ Devg0d และคืนค่า URL ---
        if devgod_response.status_code == 200:
            # คืนค่า URL ปลายทางสุดท้าย (ซึ่งมาจาก devg0d request)
            return devgod_response.url
        
        # หากสถานะสุดท้ายไม่เป็น 200 OK 
        print(f"Devg0d final status not 200 OK for {app_id}. Status: {devgod_response.status_code}")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching final Devg0d URL for {app_id}: {e}")
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

    # ตรวจสอบ Channel ID (ถ้าต้องการจำกัดช่อง ให้เอา comment ด้านล่างออก)
    # if ALLOWED_CHANNEL_ID and message.channel.id != ALLOWED_CHANNEL_ID:
    #     return

    app_id = extract_app_id(message.content)

    if app_id:
        # --- ประมวลผลคำสั่งที่ถูกต้อง ---
        
        # ส่งข้อความกำลังโหลด
        await message.channel.typing()

        steam_data = get_steam_info(app_id)
        # ใช้ฟังก์ชัน check_file_status ที่อัปเดตแล้ว
        file_url_200 = check_file_status(app_id) 
        
        # สร้าง Embed
        embed = discord.Embed(
            title=f"🔎 ข้อมูล Steam App ID: {app_id}",
            color=0x1b2838 # สี Steam Dark Blue
        )
        
        # ข้อมูลเกม
        if steam_data:
            embed.add_field(name="ชื่อเกม", value=steam_data['name'], inline=False)
            embed.add_field(name="DLCs (จาก SteamCMD)", value=f"พบ **{steam_data['dlc_count']}** รายการ", inline=True)
            embed.add_field(name="ลิงก์ Steam Store", value=f"[คลิกที่นี่](https://store.steampowered.com/app/{app_id}/)", inline=True)
            if steam_data['image']:
                embed.set_thumbnail(url=steam_data['image'])
        else:
            embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
            
        # ลิงก์ดาวน์โหลด (เฉพาะถ้าได้สถานะ 200 OK จาก Devg0d Request)
        if file_url_200:
            # แสดงผลเป็น Markdown Link [ดาวน์โหลด↗] ตามที่ร้องขอ
            embed.add_field(
                name="🔗 สถานะและลิงก์ดาวน์โหลด", 
                value=f"สถานะ: **✅ พร้อมดาวน์โหลด**\n[**ดาวน์โหลด↗**]({file_url_200})", 
                inline=False
            )
        else:
            # แสดงสถานะว่าไม่พร้อมหากไม่ได้รับ 200 OK จาก Devg0d Request (แม้ Melly จะผ่านหรือไม่ผ่านก็ตาม)
            embed.add_field(
                name="🔗 สถานะและลิงก์ดาวน์โหลด", 
                value="สถานะ: **❌ ไม่พบไฟล์/ลิงก์ไม่พร้อม**", 
                inline=False
            )
        
        await message.channel.send(embed=embed)
        
    else:
        # --- ลบข้อความที่ไม่เกี่ยวข้อง ---
        # การลบข้อความยังคงถูกปิดไว้ตามโค้ดเดิม เพื่อให้คุณสามารถทดสอบได้ง่าย
        pass
            
# --- 5. Main Execution ---

if __name__ == '__main__':
    # 1. เริ่ม Web Server Keep-Alive ใน Thread แยก
    keep_alive() 

    # 2. รัน Discord Bot ใน Main Thread
    try:
        if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            print("FATAL ERROR: Please set the DISCORD_BOT_TOKEN environment variable or change the default value.")
        else:
            bot.run(DISCORD_BOT_TOKEN)
    except discord.errors.LoginFailure:
        print("FATAL ERROR: Invalid Discord Bot Token. Please check your token.")
    except Exception as e:
        print(f"An error occurred while running the bot: {e}")
