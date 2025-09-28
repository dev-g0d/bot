import discord
from discord.ext import commands
import requests
import re
import os
import threading
from flask import Flask 

# --- 1. Flask Keep-Alive Setup ---
# สร้าง Flask App เพื่อตอบสนองต่อ Health Check ของ Render
web_app = Flask('') 

@web_app.route('/')
def home():
    """Endpoint สำหรับ Health Check ของ Render"""
    return "Discord Bot is running and ready to serve!"

def run_web_server():
    """รัน Web Server ใน Thread แยก"""
    # ดึงค่า PORT จาก Environment Variable ของ Render (ถ้ามี) หรือใช้ 8080 เป็นค่า default
    port = int(os.environ.get("PORT", 8080))
    # ปิดการแสดง log ของ Flask เพื่อให้ log ของ Discord Bot ดูง่ายขึ้น
    os.environ['WERKZEUG_RUN_MAIN'] = 'true'
    web_app.run(host='0.0.0.0', port=port)

def keep_alive():
    """เริ่ม Thread สำหรับ Web Server เพื่อป้องกันไม่ให้ Render ปิด Worker"""
    t = threading.Thread(target=run_web_server)
    t.start()

# --- 2. Configuration ---
# ดึง Discord Token จาก Environment Variables บน Render
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") 

# กำหนด ID ห้องที่อนุญาตให้บอททำงาน
# คุณสามารถตั้งค่าตัวเลข ID ห้องของคุณตรงนี้โดยตรง หรือเปลี่ยนไปดึงจาก Environment Variable ก็ได้
ALLOWED_CHANNEL_ID = 1098314625646329966  # <<<--- เปลี่ยนเป็น ID ช่องจริงของคุณ

# URL สำหรับตรวจสอบสถานะไฟล์บนเซิร์ฟเวอร์ devg0d
DEVGOD_BASE_URL = "https://devg0d.pythonanywhere.com/app_request/" 
STEAM_API_URL = "https://store.steampowered.com/api/appdetails?appids="

# ตั้งค่า Intents ที่จำเป็น
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True # ต้องเปิดใน Developer Portal
intents.guilds = True
# intents.members = True # ถูกรวมอยู่ใน intents.default() และมีการเปิดใน Developer Portal แล้ว

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
    """ดึงข้อมูลเกมจาก Steam API"""
    try:
        url = f"{STEAM_API_URL}{app_id}&cc=th&l=th"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data and data[app_id]['success']:
            details = data[app_id]['data']
            name = details.get('name', 'N/A')
            header_image = details.get('header_image', 'N/A')
            dlc_count = len(details.get('dlc', []))
            
            return {
                'name': name,
                'image': header_image,
                'dlc_count': dlc_count,
            }
        return None
    except requests.RequestException:
        return None

def check_file_status(app_id):
    """
    ตรวจสอบสถานะของ URL จากเซิร์ฟเวอร์ devg0d และตามหา URL 200 OK
    """
    check_url = f"{DEVGOD_BASE_URL}{app_id}"
    
    try:
        # ใช้ requests.get() เพื่อให้ติดตาม Redirect โดยอัตโนมัติ
        response = requests.get(check_url, allow_redirects=True, timeout=10)
        
        # ตรวจสอบสถานะการตอบกลับสุดท้าย
        if response.status_code == 200:
            # ถ้าสถานะสุดท้ายเป็น 200 (ซึ่ง requests จัดการ Redirect ให้แล้ว)
            # เราใช้ response.url ซึ่งคือ URL ปลายทางสุดท้าย (ที่เป็น 200)
            
            # ตรวจสอบว่ามีการ Redirect เกิดขึ้นหรือไม่ (เพื่อให้มั่นใจว่ามันผ่านการขอ token)
            if response.history:
                return response.url
            else:
                # ถ้าได้ 200 โดยไม่มี history อาจหมายถึงไม่มีการ Redirect token
                # เราจะถือว่าไม่พบลิงก์ที่ต้องการ
                return None
        
        return None

    except requests.exceptions.RequestException as e:
        # print(f"Request error for token: {e}") # สำหรับ debug
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

    # ตรวจสอบ Channel ID
    if ALLOWED_CHANNEL_ID and message.channel.id != ALLOWED_CHANNEL_ID:
        return

    app_id = extract_app_id(message.content)

    if app_id:
        # --- ประมวลผลคำสั่งที่ถูกต้อง ---
        
        # ส่งข้อความกำลังโหลด
        await message.channel.typing()

        steam_data = get_steam_info(app_id)
        file_url_200 = check_file_status(app_id)
        
        # สร้าง Embed
        embed = discord.Embed(
            title=f"🔎 ข้อมูล Steam App ID: {app_id}",
            color=0x1b2838 # สี Steam Dark Blue
        )
        
        # ข้อมูลเกม
        if steam_data:
            embed.add_field(name="ชื่อเกม", value=steam_data['name'], inline=False)
            embed.add_field(name="DLCs", value=f"{steam_data['dlc_count']} รายการ", inline=True)
            embed.add_field(name="ลิงก์ Steam Store", value=f"[คลิกที่นี่](https://store.steampowered.com/app/{app_id}/)", inline=True)
            if steam_data['image'] != 'N/A':
                embed.set_thumbnail(url=steam_data['image'])
        else:
            embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
            
        # ลิงก์ดาวน์โหลด
        if file_url_200:
            embed.add_field(
                name="🔗 ลิงก์ดาวน์โหลด (สถานะ 200 OK)", 
                value=f"```\n{file_url_200}\n```\n(URL นี้คือปลายทางที่ตรวจสอบแล้ว)", 
                inline=False
            )
        else:
            embed.add_field(
                name="🔗 ลิงก์ดาวน์โหลด (สถานะ)", 
                value=f"ไม่พบ URL ปลายทางสถานะ 200 OK บนเซิร์ฟเวอร์ `{DEVGOD_BASE_URL}` (อาจเป็น 404, 500 หรือไม่มีไฟล์)", 
                inline=False
            )

        await message.channel.send(embed=embed)
        
    else:
        # --- ลบข้อความที่ไม่เกี่ยวข้อง ---
        try:
            # ลบข้อความที่ไม่ใช่ App ID หรือ URL ที่ถูกต้อง
            await message.delete()
            print(f"Deleted irrelevant message from {message.author}: '{message.content}'")
        except discord.Forbidden:
            # ข้อผิดพลาดเมื่อบอทไม่มีสิทธิ์ลบข้อความ
            print(f"Error: Bot lacks permission to delete messages in channel {message.channel.id}.")
        except Exception as e:
            # ข้อผิดพลาดอื่นๆ
            print(f"An unexpected error occurred while deleting message: {e}")
            
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
