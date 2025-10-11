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
ALLOWED_CHANNEL_IDS = [1098314625646329966, 1422199765818413116]
DEVGOD_BASE_URL = "https://devg0d.pythonanywhere.com/app_request/"
STEAMCMD_API_URL = "https://api.steamcmd.net/v1/info/"
STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails?appids="
MORRENUS_GAMES_URL = "https://manifest.morrenus.xyz/api/games?t=0"

# Intents
intents = nextcord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

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

    for short, full in th_short_to_full.items():
        if short in raw_date:
            return raw_date.replace(short, full)

    try:
        dt = datetime.datetime.strptime(raw_date, "%b %d, %Y")
        return f"{dt.day} {en_to_th[dt.strftime('%b')]} {dt.year}"
    except ValueError:
        try:
            dt = datetime.datetime.strptime(raw_date, "%Y-%m-%d")
            return f"{dt.day} {en_to_th[dt.strftime('%b')]} {dt.year}"
        except ValueError:
            pass

    for eng_month, th_month in en_to_th.items():
        if eng_month in raw_date:
            return raw_date.replace(eng_month, th_month)
    return raw_date

def get_steam_info(app_id):
    release_date_thai = 'ไม่ระบุ'
    has_denuvo = False
    header_image_store = None
    name_store = 'ไม่พบแอป'
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

    return {
        'name': name_store,
        'developer': store_info.get('developer', 'ไม่ระบุ') if store_success else 'ไม่ระบุ',
        'image': header_image_store,
        'dlc_count': dlc_count_store,
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

def fetch_morrenus_database():
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
        'Cookie': os.environ.get("MORRENUS_COOKIE", "")
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Morrenus games fetch error: {e}")
        return None

def check_morrenus_status():
    url = "https://manifest.morrenus.xyz"
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def convert_download_url(url: str) -> tuple[str | None, str | None, str | None, str | None]:
    """แปลง URL จาก gofile หรือ pixeldrain เป็น URL ใหม่ พร้อมคืน file_id และ flag"""
    gofile_match = re.match(r"https://gofile\.io/d/([a-zA-Z0-9]+)", url)
    if gofile_match:
        file_id = gofile_match.group(1)
        return f"https://gf.1drv.eu.org/{file_id}", url, file_id, "🇬"
    pixeldrain_match = re.match(r"https://pixeldrain\.com/u/([a-zA-Z0-9]+)", url)
    if pixeldrain_match:
        file_id = pixeldrain_match.group(1)
        return f"https://pd.1drv.eu.org/{file_id}", url, file_id, "🇵"
    return None, None, None, None

# --- 5. Slash Commands ---
@bot.slash_command(name="gen", description="ค้นหาไฟล์จาก App ID หรือ URL")
async def gen(interaction: nextcord.Interaction, input_value: str = nextcord.SlashOption(
    name="input",
    description="ใส่ App ID หรือ URL (เช่น 730 หรือ https://store.steampowered.com/app/730/)",
    required=True
)):
    if interaction.channel_id not in ALLOWED_CHANNEL_IDS:
        await interaction.response.send_message("ไม่มีสิทธิในการใช้งาน กรุณาใช้คำสั่งที่ <#1422199765818413116>", ephemeral=True)
        return

    app_id = extract_app_id(input_value)
    if not app_id:
        await interaction.response.send_message("ไม่พบ App ID ในข้อมูลที่ให้มา!", ephemeral=True)
        return

    await interaction.response.defer()
    steam_data = get_steam_info(app_id)
    file_url_200 = check_file_status(app_id) 
    
    embed = nextcord.Embed(
        title=steam_data['name'] if steam_data['name'] != 'ไม่พบแอป' else f"App ID: {app_id}",
        description="ข้อมูลจาก Steam และสถานะไฟล์",
        color=0x1E90FF
    )
    
    if steam_data['name'] != 'ไม่พบแอป':
        embed.add_field(name="🎮 ชื่อเกม", value=steam_data['name'], inline=True)
        embed.add_field(name="🛠️ ผู้พัฒนา", value=steam_data['developer'] if steam_data['developer'] != 'ไม่ระบุ' else 'ไม่ระบุ', inline=True)
        embed.add_field(name="📅 วันวางจำหน่าย", value=steam_data['release_date'], inline=True)
        embed.add_field(
            name="📦 DLC",
            value=f"พบ {steam_data['dlc_count']} DLC" if steam_data['dlc_count'] > 0 else "ไม่พบ DLC",
            inline=True
        )
        links_value = f"[Steam Store](https://store.steampowered.com/app/{app_id}/) | [SteamDB](https://steamdb.info/app/{app_id}/)"
        if steam_data['has_denuvo']:
            links_value += "\n⚠️ ตรวจพบ Denuvo DRM"
        embed.add_field(name="🔗 ลิงก์", value=links_value, inline=False)
    else:
        embed.add_field(name="❌ สถานะ", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
    
    embed.add_field(
        name="📥 ดาวน์โหลด",
        value=f"[พร้อมดาวน์โหลด ↗]({file_url_200})" if file_url_200 else "ไม่พบไฟล์",
        inline=False
    )
    
    if steam_data['image']:
        embed.set_thumbnail(url=steam_data['image'])
    embed.set_footer(text="DEV/g0d • Solus", icon_url="https://i.imgur.com/your-icon.png")  # Replace with actual icon URL if available
    
    await interaction.followup.send(embed=embed)

@bot.slash_command(name="download", description="Bypass สำหรับ gofile หรือ pixeldrain")
async def download(interaction: nextcord.Interaction, urls: str = nextcord.SlashOption(
    name="urls",
    description="ใส่ลิงก์ gofile หรือ pixeldrain (คั่นด้วยเครื่องหมาย , หากมีหลายลิงก์)",
    required=True
)):
    if interaction.channel_id not in ALLOWED_CHANNEL_IDS:
        await interaction.response.send_message("ไม่มีสิทธิในการใช้งาน กรุณาใช้คำสั่งที่ <#1422199765818413116>", ephemeral=True)
        return

    await interaction.response.defer()

    url_list = [url.strip() for url in urls.split(",")]
    converted_urls = []
    
    for url in url_list:
        converted_url, original_url, file_id, flag = convert_download_url(url)
        if converted_url and original_url and file_id and flag:
            converted_urls.append((converted_url, original_url, file_id, flag))
    
    embed = nextcord.Embed(
        title="📥 Bypass Download Limiter",
        color=0x00FF00 if converted_urls else 0xFF0000
    )

    if converted_urls:
        for converted_url, original_url, file_id, flag in converted_urls:
            embed.add_field(
                name="",
                value=f"🔗 {flag} [/{file_id}]({original_url}) | [Bypass ↗]({converted_url})",
                inline=False
            )
    else:
        embed.add_field(
            name="",
            value="❌ รองรับเฉพาะลิงก์ gofile และ pixeldrain เท่านั้น",
            inline=False
        )

    embed.set_footer(text="Discord • DEV/g0d • GameDrive.Org")
    await interaction.followup.send(embed=embed)

@bot.slash_command(name="info", description="แสดงข้อมูล Solus Database")
async def info(interaction: nextcord.Interaction):
    if interaction.channel_id not in ALLOWED_CHANNEL_IDS:
        await interaction.response.send_message("ไม่มีสิทธิในการใช้งาน กรุณาใช้คำสั่งที่ <#1422199765818413116>", ephemeral=True)
        return

    await interaction.response.defer()

    morrenus_data = fetch_morrenus_database()
    status = check_morrenus_status()

    embed = nextcord.Embed(
        title="📝 Solus Database",
        color=0x00FF00 if status else 0xFF0000
    )

    total_apps = morrenus_data.get('total', 'ไม่ระบุ') if morrenus_data else 'ไม่ระบุ'
    total_dlc = morrenus_data.get('total_dlc', 'ไม่ระบุ') if morrenus_data else 'ไม่ระบุ'
    if morrenus_data and isinstance(total_apps, (int, float)) and isinstance(total_dlc, (int, float)):
        total_combined = total_apps + total_dlc
    else:
        total_combined = 'ไม่ระบุ'
    status_text = "🟢 ทำงาน" if status else "🔴 ไม่ทำงาน"

    embed.add_field(name="", value=f"📦 แอปหลักทั้งหมด: {total_apps}", inline=False)
    embed.add_field(name="", value=f"📦 DLC ทั้งหมด: {total_dlc}", inline=False)
    embed.add_field(name="", value=f"📦 รวมแอปทั้งหมด: {total_combined}", inline=False)
    embed.add_field(name="", value=f"📊 Limit: Unlimited (ไม่จำกัด)", inline=False)
    embed.add_field(name="", value=f"📊 Status: {status_text}", inline=False)

    embed.set_footer(text="Discord • DEV/g0d • Solus")

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
