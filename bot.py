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
# **สำคัญ:** ต้องตั้งค่า DISCORD_BOT_TOKEN ใน Environment Variables ของ Render
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") 

# กำหนด ID ห้องที่อนุญาตให้บอททำงาน
# **สำคัญ:** เปลี่ยนเลขนี้เป็น ID ช่องจริงของคุณ
ALLOWED_CHANNEL_ID = 1098314625646329966  

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
    # --- แก้ไข: ใช้ argument 'message_content' แทน 'message.content' เพื่อแก้ NameError/Scope Issue ---
    match = re.search(r'(?:steamdb\.info\/app\/|store\.steampowered\.com\/app\/)(\d+)', message_content)
    if match:
        return match.group(1)
    return None

def get_steam_info(app_id):
    """ดึงข้อมูลเกมและนับ DLCs จาก SteamCMD API"""
    try:
        url = f"{STEAMCMD_API_URL}{app_id}"
        # เพิ่ม User-Agent เพื่อทำตัวเหมือน Browser
        headers = {'User-Agent': 'DiscordBot-SteamInfo/1.0'}
        response = requests.get(url, headers=headers, timeout=7)
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
            header_image = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/{header_image_hash}" if header_image_hash else None
            
            # --- แก้ไขตรรกะการนับ DLCs ให้แม่นยำ ---
            dlc_list_str = extended.get('listofdlc', '')
            # แยกสตริงด้วย comma และกรองเอาเฉพาะรายการที่ไม่ใช่สตริงว่าง
            dlc_items = [item for item in dlc_list_str.split(',') if item.strip()]
            dlc_count = len(dlc_items)
            # ----------------------------------------
            
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
    ตรวจสอบสถานะของ URL จากเซิร์ฟเวอร์ devg0d และตามหา URL ที่ให้สถานะ 200 OK
    คืนค่า URL ปลายทางสุดท้าย (200 OK) หรือ None
    """
    check_url = f"{DEVGOD_BASE_URL}{app_id}"
    
    try:
        # เพิ่ม User-Agent เพื่อทำตัวเหมือน Browser
        headers = {'User-Agent': 'DiscordBot-Downloader/1.0'}
        # requests.get พร้อม allow_redirects=True จะติดตาม 302 ไปจนเจอ URL สุดท้าย
        response = requests.get(check_url, headers=headers, allow_redirects=True, timeout=10)
        
        # คืนค่า URL ปลายทางสุดท้าย (response.url) ก็ต่อเมื่อสถานะสุดท้ายคือ 200 OK
        if response.status_code == 200:
            return response.url
        
        # --- ปรับปรุงการ Log เพื่อการ Debug บน Render ---
        print(f"--- File Status Check Failed for App ID: {app_id} ---")
        print(f"Final Status Code Received: {response.status_code}")
        print(f"Final URL Reached: {response.url}")
        print("-----------------------------------------------------")
        # ----------------------------------------------------
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error checking file status for {app_id}: {e}")
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
        # ลบข้อความที่ไม่เกี่ยวข้องในช่องอื่น (เพิ่มมาจากการแก้ไขครั้งก่อน)
        try:
            await message.delete()
        except discord.Forbidden:
            print(f"Error: Bot lacks permission to delete messages in channel {message.channel.id}.")
        except Exception as e:
            print(f"An unexpected error occurred while deleting message in wrong channel: {e}")
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
            embed.add_field(name="DLCs (จาก SteamCMD)", value=f"พบ **{steam_data['dlc_count']}** รายการ", inline=True)
            embed.add_field(name="ลิงก์ Steam Store", value=f"[คลิกที่นี่](https://store.steampowered.com/app/{app_id}/)", inline=True)
            if steam_data['image']:
                embed.set_thumbnail(url=steam_data['image'])
        else:
            embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
            
        # --- การแสดงผลลิงก์ดาวน์โหลดที่ปรับปรุงใหม่ ---
        if file_url_200:
            # สถานะ 200 OK: แสดงลิงก์ Markdown
            embed.add_field(
                name="🔗 ลิงก์ดาวน์โหลด (พร้อม)", 
                value=f"[**ดาวน์โหลด↗**]({file_url_200})", 
                inline=False
            )
        else:
            # สถานะอื่นที่ไม่ใช่ 200 OK: แสดงข้อความแจ้ง
            # **สำคัญ:** เราทราบว่าใน Browser ได้ 200 OK แต่ในบอทไม่ได้
            # การเพิ่ม Log ใน check_file_status จะช่วยให้เราเห็น Status Code ที่บอทได้รับ
            embed.add_field(
                name="🔗 ลิงก์ดาวน์โหลด (สถานะ)", 
                value="**ไม่พบ URL ปลายทางสถานะ 200 OK** (โปรดตรวจสอบ Log ของ Render)", 
                inline=False
            )
        # ---------------------------------------------
        
        # ลบข้อความคำสั่งของผู้ใช้
        try:
            await message.delete()
        except discord.Forbidden:
            print(f"Error: Bot lacks permission to delete message after processing in channel {message.channel.id}.")
        except Exception as e:
            print(f"An unexpected error occurred while deleting message after processing: {e}")
        
        await message.channel.send(embed=embed)
        
    else:
        # --- ลบข้อความที่ไม่เกี่ยวข้อง (ไม่เป็น App ID) ---
        try:
            await message.delete()
        except discord.Forbidden:
            print(f"Error: Bot lacks permission to delete messages in channel {message.channel.id}.")
        except Exception as e:
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
