import nextcord
from nextcord.ext import commands
import requests
import re
import os
import threading
from flask import Flask 
import datetime
import zipfile
import io
import tempfile

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
ALLOWED_CHANNEL_IDS = [1098314625646329966, 1422199765818413116]  # รองรับหลายชาแนล
DEVGOD_BASE_URL = "https://devg0d.pythonanywhere.com/app_request/"  # ใช้ส่ง URL ให้ยูเซอร์
STEAMCMD_API_URL = "https://api.steamcmd.net/v1/info/"
STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails?appids="
MORRENUS_API_URL = "https://manifest.morrenus.xyz/api/game/"  # URL สำหรับ Morrenus
MORRENUS_GAMES_URL = "https://manifest.morrenus.xyz/api/games?t=0"  # URL สำหรับ /info

# Intents
intents = nextcord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True  # เพิ่ม intents สำหรับดึงข้อมูลสมาชิก

bot = commands.Bot(command_prefix="/", intents=intents)

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
    if raw_date == 'ไม่ระบุ' or raw_date.lower() == 'tba':
        return 'ไม่ระบุ'

    # กรณีภาษาไทยย่อ เช่น "28 เม.ย. 2017"
    for short, full in th_short_to_full.items():
        if short in raw_date:
            return raw_date.replace(short, full)

    # กรณีภาษาอังกฤษ เช่น "Apr 27, 2017" หรือ "2025-06-12"
    try:
        # ลอง parse รูปแบบ "Month Day, Year" (เช่น "Apr 27, 2017")
        dt = datetime.datetime.strptime(raw_date, "%b %d, %Y")
        return f"{dt.day} {en_to_th[dt.strftime('%b')]} {dt.year}"
    except ValueError:
        try:
            # ลอง parse รูปแบบ "YYYY-MM-DD" (เช่น "2025-06-12")
            dt = datetime.datetime.strptime(raw_date, "%Y-%m-%d")
            return f"{dt.day} {en_to_th[dt.strftime('%b')]} {dt.year}"
        except ValueError:
            pass

    # กรณีอื่น ๆ ที่ parse ไม่ได้ (เช่น "Coming Soon" หรือ format อื่น) ส่งกลับเป็นไทยเต็มถ้ามี หรือไม่ก็ raw
    for eng_month, th_month in en_to_th.items():
        if eng_month in raw_date:
            return raw_date.replace(eng_month, th_month)
    return raw_date

def get_steam_info(app_id):
    # 1. ลองดึงจาก Morrenus ก่อน (แค่ JSON ไม่มีไฟล์)
    morrenus_data = fetch_morrenus_info(app_id)
    release_date_thai = 'ไม่ระบุ'  # Default value
    has_denuvo = False

    # 2. ดึงข้อมูลจาก Steam เสมอเพื่อให้ได้ release_date และ has_denuvo
    header_image_store = None
    name_store = None
    dlc_count_store = 0
    store_success = False
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

    # 3. ถ้ามี Morrenus ใช้ข้อมูลจาก Morrenus เป็นหลักสำหรับบางส่วน
    if morrenus_data:
        dlc_status = morrenus_data.get('dlc_status', {})
        total_dlc = dlc_status.get('total_dlc', 0)
        included_dlc = dlc_status.get('included_dlc', 0)
        missing_dlc = total_dlc - included_dlc

        return {
            'name': morrenus_data.get('name', name_store),
            'developer': morrenus_data.get('developer', 'ไม่ระบุ'),
            'image': morrenus_data.get('header_image', header_image_store),
            'dlc_count': total_dlc,
            'included_dlc': included_dlc,
            'missing_dlc': missing_dlc,
            'release_date': release_date_thai,
            'has_denuvo': has_denuvo,
        }

    # 4. ถ้าไม่มี Morrenus ใช้ข้อมูลจาก Steam
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
            dlc_items = [item.strip() for item in dlc_list_str.split(',') if item.strip()]
            dlc_count_cmd = len(dlc_items)
    except requests.RequestException as e:
        print(f"SteamCMD fetch error: {e}")

    # --- รวมข้อมูลจาก Steam ---
    name = name_store if store_success else name_cmd
    dlc_count = dlc_count_cmd if cmd_success and dlc_count_cmd > 0 else dlc_count_store
    header_image = header_image_store or (f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/{header_image_hash}" if header_image_hash else None)

    return {
        'name': name,
        'developer': 'ไม่ระบุ',
        'image': header_image,
        'dlc_count': dlc_count,
        'included_dlc': 0,  # Default ถ้าไม่มี Morrenus
        'missing_dlc': dlc_count if dlc_count > 0 else 0,  # Default ถ้าไม่มี Morrenus
        'release_date': release_date_thai,
        'has_denuvo': has_denuvo,
    }

def fetch_morrenus_database():
    # ฟังก์ชันดึงข้อมูลจาก Morrenus games API
    url = MORRENUS_GAMES_URL
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'max-age=0',
        'Sec-Ch-Ua': '"Chromium";v="140", "Not_A Brand";v="24", "Google Chrome";v="140"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
        'Cookie': os.environ.get("MORRENUS_COOKIE", "session=eyJhY2Nlc3NfdG9rZW4iOiAiZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5LmV5SjFjMlZ5WDJsa0lqb2lNVEkzTmprMk1qVXlNek15TkRZeE5qZzBNU0lzSW5WelpYSnVZVzFsSWpvaU9XY3daQ0lzSW1ScGMyTnlhVzFwYm1GMGIzSWlPaUl3SWl3aVlYWmhkR0Z5SWpvaU1qSTRPVFUyTURWbVltWmhZVEptTkROaVpXRmtZamMyWVdJek1tWTNZekFpTENKb2FXZG9aWE4wWDNKdmJHVWlPaUpUYjNCb2FXVWdkR2hsSUVOaGRDSXNJbkp2YkdWZmJHbHRhWFFpT2pJMUxDSnliMnhsWDJ4bGRtVnNJam94TENKaGJHeGZjbTlzWlhNaU9sc2lSMkZ0Zl5CT1pYZHpJaXdpUVc1dWIzVnVZMlZ0Wlc1MGN5SXNJbE52Y0docFpTQjBhR1VnUTJGMElsMHNJbVY0Y0NJNk1UYzFPVFUwTkRBNE0zMC5JR3N4VVY1ZGFaZUlsdlBLZ1g0aGN2Sm01MVZtVHd3ek1ZYUtoQ3JGbEdFIn0=.aN8zZw.oHnSL1QtpzM31BggieAKzO49i5U")
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Morrenus games fetch error: {e}")
        return None

def check_morrenus_status():
    # เช็คสถานะเว็บ Morrenus
    url = "https://manifest.morrenus.xyz"
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

# --- 5. Slash Commands ---
@bot.slash_command(name="info", description="แสดงข้อมูล Morrenus Database")
async def info(interaction: nextcord.Interaction):
    if interaction.channel_id not in ALLOWED_CHANNEL_IDS:
        await interaction.response.send_message("ไม่มีสิทธิในการใช้งาน กรุณาใช้คำสั่งที่ <#1422199765818413116>", ephemeral=True)
        return

    await interaction.response.defer()  # แสดงว่ากำลังประมวลผล

    morrenus_data = fetch_morrenus_database()
    status = check_morrenus_status()

    embed = nextcord.Embed(
        title="📝 Morrenus Database",
        color=0x00FF00 if status else 0xFF0000
    )

    total_apps = morrenus_data.get('total', 'ไม่ระบุ') if morrenus_data else 'ไม่ระบุ'
    total_dlc = morrenus_data.get('total_dlc', 'ไม่ระบุ') if morrenus_data else 'ไม่ระบุ'
    status_text = "🟢 ทำงาน" if status else "🔴 ไม่ทำงาน"

    embed.add_field(name="📦 แอปทั้งหมด", value=total_apps, inline=False)
    embed.add_field(name="📦 DLC ทั้งหมด", value=total_dlc, inline=False)
    embed.add_field(name="Status", value=status_text, inline=False)
    embed.add_field(name="🔗 Website", value="https://manifest.morrenus.xyz", inline=False)
    embed.set_footer(text="discord • DEV/g0d • Morrenus")

    await interaction.followup.send(embed=embed)

# --- 6. Discord Events ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('Bot is ready and running!')
    await bot.change_presence(activity=nextcord.Activity(type=nextcord.ActivityType.watching, name="24/7 for Manifest"))

# --- 7. Main Execution ---
if __name__ == '__main__':
    keep_alive() 
    try:
        if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            print("FATAL ERROR: Please set the DISCORD_BOT_TOKEN environment variable or change the default value.")
        else:
            bot.run(DISCORD_BOT_TOKEN)
    except nextcord.errors.LoginFailure:
        print("FATAL ERROR: Invalid Discord Bot Token. Please check your token.")
    except Exception as e:
        print(f"An error occurred while running the bot: {e}")
