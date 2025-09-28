import discord
from discord.ext import commands
import requests
import re
import os
import threading
from flask import Flask # นำเข้า Flask

# --- Flask Keep-Alive Setup ---
# สร้าง Flask App เพื่อตอบสนองต่อ Health Check ของ Render
web_app = Flask('') 

@web_app.route('/')
def home():
    """หน้า Home สำหรับ Health Check ของ Render"""
    return "Discord Bot is running and ready to serve!"

def run_web_server():
    """รัน Web Server ใน Thread แยก"""
    # Render มักจะใช้ Environment Variable ในการกำหนด Port ที่ต้อง Listen
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

def keep_alive():
    """เริ่ม Thread สำหรับ Web Server"""
    t = threading.Thread(target=run_web_server)
    t.start()

# --- Configuration ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") 
# กำหนด ID ห้องที่อนุญาตให้บอททำงาน
# หากต้องการรันบอทในทุกห้อง ให้ตั้งค่าเป็น None หรือลบเงื่อนไขนี้ออก
ALLOWED_CHANNEL_ID = 1098314625646329966  # เปลี่ยนเป็น ID ช่องจริงของคุณ

# URL สำหรับตรวจสอบสถานะไฟล์
DEVGOD_BASE_URL = "https://devg0d.pythonanywhere.com/app_request/" 
STEAM_API_URL = "https://store.steampowered.com/api/appdetails?appids="

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- Helper Functions (เหมือนเดิม) ---
def extract_app_id(message_content):
    """ดึง App ID จากข้อความที่ป้อน (เลขล้วน หรือ URL Steam/SteamDB)"""
    if message_content.isdigit():
        return message_content
    match = re.search(r'(?:steamdb\.info\/app\/|store\.steampowered\.com\/app\/)(\d+)', message_content)
    if match:
        return match.group(1)
    return None

def get_steam_info(app_id):
    """ดึงข้อมูลเกมจาก Steam API"""
    try:
        url = f"{STEAM_API_URL}{app_id}&cc=th&l=th"
        response = requests.get(url)
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
    """ตรวจสอบสถานะของ URL จากเซิร์ฟเวอร์ devg0d และตามหา URL 200 OK"""
    check_url = f"{DEVGOD_BASE_URL}{app_id}"
    
    try:
        # requests จะตาม Redirect ให้อัตโนมัติและ response.url จะเป็น URL ปลายทาง 200 OK
        response = requests.get(check_url, allow_redirects=True, timeout=10)
        
        if response.status_code == 200 and response.history:
            # ตรวจสอบว่ามีการ Redirect เกิดขึ้น (response.history) และสถานะสุดท้ายคือ 200
            return response.url
        
        # ถ้าไม่มีการ Redirect หรือสถานะไม่เป็น 200 ถือว่าไม่พบลิงก์ที่ถูกต้อง
        return None

    except requests.exceptions.RequestException:
        return None


# --- Discord Events ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('Bot is ready!')

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # ตรวจสอบ Channel ID (รองรับการตั้งค่าเป็น None ในอนาคตได้)
    if ALLOWED_CHANNEL_ID and message.channel.id != ALLOWED_CHANNEL_ID:
        return

    app_id = extract_app_id(message.content)

    if app_id:
        # --- ประมวลผลคำสั่งที่ถูกต้อง ---
        steam_data = get_steam_info(app_id)
        file_url_200 = check_file_status(app_id)
        
        embed = discord.Embed(
            title=f"🔎 ข้อมูล Steam App ID: {app_id}",
            color=0x1b2838 
        )
        
        if steam_data:
            embed.add_field(name="ชื่อเกม", value=steam_data['name'], inline=False)
            embed.add_field(name="DLCs", value=f"{steam_data['dlc_count']} รายการ", inline=True)
            embed.add_field(name="ลิงก์ Steam Store", value=f"[คลิกที่นี่](https://store.steampowered.com/app/{app_id}/)", inline=True)
            if steam_data['image'] != 'N/A':
                embed.set_thumbnail(url=steam_data['image'])
        else:
            embed.add_field(name="สถานะ", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
            
        if file_url_200:
            embed.add_field(
                name="🔗 ลิงก์ดาวน์โหลด (สถานะ 200 OK)", 
                value=f"```\n{file_url_200}\n```\n(URL นี้เป็น URL ปลายทางที่ถูกต้องแล้ว)", 
                inline=False
            )
        else:
            embed.add_field(
                name="🔗 ลิงก์ดาวน์โหลด (สถานะ)", 
                value=f"ไม่พบ URL ปลายทางสถานะ 200 OK บนเซิร์ฟเวอร์ `{DEVGOD_BASE_URL}` (อาจเป็นสถานะ 404, 500 หรือไม่มีไฟล์)", 
                inline=False
            )

        await message.channel.send(embed=embed)
        
    else:
        # --- ลบข้อความที่ไม่เกี่ยวข้อง ---
        try:
            await message.delete()
            print(f"Deleted message from {message.author}: '{message.content}'")
        except discord.Forbidden:
            print(f"Error: Bot does not have permission to delete messages in channel {message.channel.id}. Check bot permissions.")
        except Exception as e:
            print(f"An unexpected error occurred while deleting message: {e}")
            
# --- Main Execution ---

if __name__ == '__main__':
    # 1. เริ่ม Web Server Keep-Alive ใน Thread แยก
    keep_alive() 

    # 2. รัน Discord Bot ใน Main Thread
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except discord.errors.LoginFailure:
        print("FATAL ERROR: Invalid Discord Bot Token. Please check your DISCORD_BOT_TOKEN.")
    except Exception as e:
        print(f"An error occurred while running the bot: {e}")
