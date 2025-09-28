import discord
from discord.ext import commands
import requests
import re
import os

# --- Configuration ---
# แนะนำให้ใช้ Environment Variable ในการเก็บ Token เมื่อรันบน Render
# หากทดสอบในเครื่อง ให้แทนที่ด้วย Token จริง
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE") 
# กำหนด ID ห้องที่อนุญาตให้บอททำงาน (ถ้ามีหลายห้องให้ใส่เป็น list)
ALLOWED_CHANNEL_ID = 1098314625646329966  # เปลี่ยนเป็น ID ช่องจริงของคุณ

# URL สำหรับตรวจสอบสถานะไฟล์บนเซิร์ฟเวอร์ของคุณ
DEVGOD_BASE_URL = "https://devg0d.pythonanywhere.com/app_request/" 
# Steam API endpoint (เราใช้ Steam Store API ที่ไม่ต้องใช้ Key)
STEAM_API_URL = "https://store.steampowered.com/api/appdetails?appids="

# ตั้งค่า Intents ที่จำเป็นสำหรับการทำงาน (ต้องเปิดในหน้า Developer Portal)
# - messages: สำหรับอ่านข้อความ
# - members (ถ้าต้องการใช้): สำหรับการลบข้อความ (บางครั้งต้องการ Member Intents)
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True # ต้องเปิดเพื่ออ่านเนื้อหาข้อความ
intents.guilds = True

# สร้าง Client
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Helper Functions ---

def extract_app_id(message_content):
    """ดึง App ID จากข้อความที่ป้อน (เลขล้วน หรือ URL Steam/SteamDB)"""
    
    # 1. ตรวจสอบว่าเป็นตัวเลขล้วน (App ID)
    if message_content.isdigit():
        return message_content
    
    # 2. ตรวจสอบว่าเป็น Steam/SteamDB URL
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
            
            # นับจำนวน DLCs (ถ้ามี)
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
    ตรวจสอบสถานะของ URL จากเซิร์ฟเวอร์ devg0d
    ถ้าสถานะเป็น 302 (Redirect) จะตามไปหา URL ปลายทาง (200 OK)
    และส่ง URL 200 นั้นกลับมา
    """
    check_url = f"{DEVGOD_BASE_URL}{app_id}"
    
    try:
        # ใช้ requests.head เพื่อให้เร็วกว่า แต่ต้องตั้งค่า allow_redirects=False เพื่อให้ตรวจสอบ 302 ได้
        # หรือใช้ requests.get และตรวจสอบ history (วิธีนี้ชัวร์กว่าสำหรับกรณีที่มี redirect ซ้อน)
        response = requests.get(check_url, allow_redirects=True, timeout=10)
        
        # ตรวจสอบสถานะการตอบกลับ
        if response.status_code == 200:
            # ถ้าสถานะ 200 แสดงว่า URL ปลายทางอยู่ที่นี่
            # ถ้ามีการ Redirect เกิดขึ้น response.url คือ URL ปลายทาง 200 OK
            if response.history:
                return response.url
            else:
                # กรณีที่ไม่เกิดการ Redirect (เช่น App ID ใช้งานไม่ได้)
                return None 
        
        elif response.status_code == 302 and response.headers.get('Location'):
            # (กรณีนี้ไม่น่าเกิดเพราะ allow_redirects=True แต่เผื่อไว้)
            # ถ้าเป็น 302 และไม่มีการตาม Redirect ให้ตามไปเอง
            final_response = requests.get(response.headers['Location'], timeout=10)
            if final_response.status_code == 200:
                return final_response.url

        return None

    except requests.exceptions.RequestException:
        return None


# --- Discord Events ---

@bot.event
async def on_ready():
    """แจ้งเมื่อบอทพร้อมใช้งาน"""
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('Bot is ready!')

@bot.event
async def on_message(message):
    """จัดการข้อความที่เข้ามาในช่องที่กำหนด"""
    
    # ไม่ต้องประมวลผลข้อความของบอทเอง
    if message.author.bot:
        return

    # ตรวจสอบว่าข้อความมาจากช่องที่อนุญาตหรือไม่
    # ถ้า ALLOWED_CHANNEL_ID เป็นตัวเลขเดียว:
    if message.channel.id != ALLOWED_CHANNEL_ID:
        return

    # 1. พยายามดึง App ID จากข้อความ
    app_id = extract_app_id(message.content)

    if app_id:
        # --- ประมวลผลคำสั่งที่ถูกต้อง ---
        
        # ดึงข้อมูลเกม Steam
        steam_data = get_steam_info(app_id)
        
        # ตรวจสอบสถานะไฟล์จากเซิร์ฟเวอร์ devg0d
        file_url_200 = check_file_status(app_id)
        
        embed = discord.Embed(
            title=f"🔎 ข้อมูล Steam App ID: {app_id}",
            color=0x1b2838 # สี Steam Dark Blue
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
            # ลบข้อความถ้าข้อความนั้นไม่ใช่ App ID หรือ URL ที่ถูกต้อง
            await message.delete()
            print(f"Deleted message from {message.author}: '{message.content}'")
        except discord.Forbidden:
            # จัดการข้อผิดพลาดถ้าบอทไม่มีสิทธิ์ลบ
            print(f"Error: Bot does not have permission to delete messages in channel {message.channel.id}.")
        except Exception as e:
            print(f"An unexpected error occurred while deleting message: {e}")
            
# รันบอท (ใช้ Token จาก Environment Variable)
try:
    bot.run(DISCORD_BOT_TOKEN)
except discord.errors.LoginFailure:
    print("FATAL ERROR: Invalid Discord Bot Token. Please check your DISCORD_BOT_TOKEN.")
except Exception as e:
    print(f"An error occurred while running the bot: {e}")
