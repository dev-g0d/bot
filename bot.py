import nextcord
from nextcord.ext import commands
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
ALLOWED_CHANNEL_IDS = [1098314625646329966, 1422199765818413116]
STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails?appids="

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
    return match.group(1) if match else None

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
    header_image_store = None
    name_store = 'ไม่พบแอป'
    dlc_count_store = 0
    store_success = False

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
            dlc_count_store = len(store_info.get("dlc", []))
            release_date_thai = fetch_release_date_from_store_data(store_info)
    except requests.RequestException:
        pass

    return {
        'name': name_store,
        'image': header_image_store,
        'dlc_count': dlc_count_store,
        'release_date': release_date_thai,
    }

def check_file_status(app_id: str) -> str | None:
    url = f"https://devg0d.pythonanywhere.com/app_request/{app_id}"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, allow_redirects=True)
        if response.status_code == 200 and "content-disposition" in response.headers:
            return response.url
    except requests.RequestException:
        pass
    return None

def convert_download_url(url: str) -> tuple[str | None, str | None, str | None, str | None]:
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
        title=f"🔎 ข้อมูล Steam App ID: {app_id}",
        color=0x00FF00 if file_url_200 else 0xFF0000
    )
    
    if steam_data:
        embed.add_field(name="ชื่อแอป", value=steam_data['name'], inline=False)
        if steam_data['dlc_count'] > 0:
            embed.add_field(
                name="",
                value=f"📦 สถานะ DLC: ✅ พบ DLC\n(ไม่ทราบจำนวนDLCที่พบและสูญหาย)",
                inline=False
            )
        else:
            embed.add_field(
                name="",
                value="📦 สถานะ DLC: ℹ️ ไม่พบ DLC",
                inline=False
            )
        embed.add_field(name="วันวางจำหน่าย", value=steam_data['release_date'], inline=False)
        links_value = f"[Steam Store](https://store.steampowered.com/app/{app_id}/) | [SteamDB](https://steamdb.info/app/{app_id}/)"
        embed.add_field(name="Links", value=links_value, inline=False)
        
        if steam_data['image']:
            embed.set_image(url=steam_data['image'])
            embed.set_footer(text="Discord • DEV/g0d • Solus")
    else:
        embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
        embed.set_footer(text="Discord • DEV/g0d • Solus")
        
    if file_url_200:
        embed.add_field(
            name="", 
            value=f"**📥 สถานะไฟล์:** ✅ [**พร้อมดาวน์โหลด↗**]({file_url_200})", 
            inline=False
        )
    else:
        embed.add_field(
            name="📥 สถานะไฟล์: ❌ ไม่พบไฟล์", 
            value="", 
            inline=False
        )
    
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

    embed = nextcord.Embed(
        title="📝 Solus Database",
        color=0x00FF00
    )

    embed.add_field(name="", value="📦 แอปหลักทั้งหมด: ไม่ระบุ", inline=False)
    embed.add_field(name="", value="📦 DLC ทั้งหมด: ไม่ระบุ", inline=False)
    embed.add_field(name="", value="📦 รวมแอปทั้งหมด: ไม่ระบุ", inline=False)
    embed.add_field(name="", value="📊 Limit: Unlimited (ไม่จำกัด)", inline=False)
    embed.add_field(name="", value="📊 Status: 🟢 ทำงาน", inline=False)

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
    if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("FATAL ERROR: Please set the DISCORD_BOT_TOKEN environment variable or change the default value.")
    else:
        bot.run(DISCORD_BOT_TOKEN)
