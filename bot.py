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

def fetch_morrenus_info(app_id):
    # ฟังก์ชันนี้แค่ดึง JSON จาก Morrenus API ไม่ดึงไฟล์อะไรทั้งสิ้น
    url = f"{MORRENUS_API_URL}{app_id}"
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
        'Cookie': os.environ.get("MORRENUS_COOKIE", "session=eyJhY2Nlc3NfdG9rZW4iOiAiZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5LmV5SjFjMlZ5WDJsa0lqb2lNVEkzTmprMk1qVXlNek15TkRZeE5qZzBNU0lzSW5WelpYSnVZVzFsSWpvaU9XY3daQ0lzSW1ScGMyTnlhVzFwYm1GMGIzSWlPaUl3SWl3aVlYWmhkR0Z5SWpvaU1qSTRPVFUyTURWbVltWmhZVEptTkROaVpXRmtZamMyWVdJek1tWTNZekFpTENKb2FXZG9aWE4wWDNKdmJHVWlPaUpUYjNCb2FXVWdkR2hsSUVOaGRDSXNJbkp2YkdWZmJHbHRhWFFpT2pJMUxDSnliMnhsWDJ4bGRtVnNJam94TENKaGJHeGZjbTlzWlhNaU9sc2lSMkZ0WlNCT1pYZHpJaXdpUVc1dWIzVnVZMlZ0Wlc1MGN5SXNJbE52Y0docFpTQjBhR1VnUTJGMElsMHNJbVY0Y0NJNk1UYzFPVFUwTkRBNE0zMC5JR3N4VVY1ZGFaZUlsdlBLZ1g0aGN2Sm01MVZtVHd3ek1ZYUtoQ3JGbEdFIn0=.aN8zZw.oHnSL1QtpzM31BggieAKzO49i5U")
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Morrenus fetch error: {e}")
        return None

def get_steam_info(app_id):
    # 1. ลองดึงจาก Morrenus ก่อน (แค่ JSON ไม่มีไฟล์)
    morrenus_data = fetch_morrenus_info(app_id)
    release_date_thai = 'ไม่ระบุ'  # Default value
    has_denuvo = False

    if morrenus_data:
        # ดึงข้อมูลจาก Morrenus และคำนวณ DLC ตามที่มึงอยากได้
        dlc_status = morrenus_data.get('dlc_status', {})
        total_dlc = dlc_status.get('total_dlc', 0)
        included_dlc = dlc_status.get('included_dlc', 0)
        missing_dlc = total_dlc - included_dlc  # คำนวณสูญหาย

        return {
            'name': morrenus_data.get('name', 'ไม่พบแอป'),
            'developer': morrenus_data.get('developer', 'ไม่ระบุ'),  # เพิ่มผู้พัฒนา
            'image': morrenus_data.get('header_image'),
            'dlc_count': total_dlc,
            'included_dlc': included_dlc,  # จำนวนที่พบ
            'missing_dlc': missing_dlc,    # จำนวนที่สูญหาย
            'release_date': release_date_thai,  # ยังไม่กำหนด จะดึงจาก Steam ด้านล่าง
            'has_denuvo': has_denuvo,
        }

    # 2. ถ้า Morrenus ไม่ได้ หรือเพื่อดึง release_date และ has_denuvo จาก Steam
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

    # --- รวมข้อมูล: prioritize Store สำหรับส่วนใหญ่ แต่ DLC prioritize CMD ถ้ามี ---
    name = morrenus_data.get('name', name_store if store_success else name_cmd)
    dlc_count = morrenus_data.get('total_dlc', dlc_count_cmd if cmd_success and dlc_count_cmd > 0 else dlc_count_store)
    header_image = morrenus_data.get('header_image', header_image_store or (f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/{header_image_hash}" if header_image_hash else None))
    developer = morrenus_data.get('developer', 'ไม่ระบุ') if morrenus_data else 'ไม่ระบุ'

    return {
        'name': name,
        'developer': developer,
        'image': header_image,
        'dlc_count': dlc_count if morrenus_data else dlc_count,
        'included_dlc': morrenus_data.get('included_dlc', 0) if morrenus_data else 0,
        'missing_dlc': morrenus_data.get('missing_dlc', 0) if morrenus_data else (dlc_count - 0) if dlc_count > 0 else 0,
        'release_date': release_date_thai,
        'has_denuvo': has_denuvo,
    }

def check_file_status(app_id: str) -> str | None:
    url = f"{DEVGOD_BASE_URL}{app_id}"  # ยังคงใช้ DEVGOD ตามเดิม
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        final_url = response.url
        if response.status_code == 200 and "content-disposition" in response.headers:
            return final_url
    except requests.RequestException:
        return None
    return None

def download_and_extract_lua(app_id: str) -> tuple[str | None, str | None]:
    """
    ดึง final URL จาก check_file_status และดาวน์โหลดไฟล์ ZIP เพื่อแตกไฟล์ .lua
    """
    # ดึง final URL จาก check_file_status
    final_url = check_file_status(app_id)
    if not final_url:
        return None, None

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(final_url, headers=headers, timeout=15)
        response.raise_for_status()

        # ใช้ BytesIO เพื่อจัดการไฟล์ ZIP ในหน่วยความจำ
        with io.BytesIO(response.content) as zip_buffer:
            with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                # หาไฟล์ .lua ใน ZIP
                lua_file = next((f for f in zip_ref.namelist() if f.endswith('.lua')), None)
                if lua_file:
                    # อ่านเนื้อหาไฟล์ .lua
                    with zip_ref.open(lua_file) as lua_content:
                        # สร้างไฟล์ชั่วคราวเพื่อส่งผ่าน Discord
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.lua') as temp_file:
                            temp_file.write(lua_content.read())
                            temp_file_path = temp_file.name
                    return lua_file, temp_file_path
        return None, None
    except (requests.RequestException, zipfile.BadZipFile) as e:
        print(f"Error downloading or extracting ZIP: {e}")
        return None, None

def list_files_in_zip(app_id: str) -> list[str] | None:
    """
    ดึง final URL จาก check_file_status และคืนรายชื่อไฟล์ทั้งหมดใน ZIP
    """
    final_url = check_file_status(app_id)
    if not final_url:
        return None

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(final_url, headers=headers, timeout=15)
        response.raise_for_status()

        # ใช้ BytesIO เพื่อจัดการไฟล์ ZIP ในหน่วยความจำ
        with io.BytesIO(response.content) as zip_buffer:
            with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                # ดึงรายชื่อไฟล์ทั้งหมดใน ZIP
                return zip_ref.namelist()
        return None
    except (requests.RequestException, zipfile.BadZipFile) as e:
        print(f"Error downloading or listing files in ZIP: {e}")
        return None

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

    await interaction.response.defer()  # แสดงว่ากำลังประมวลผล
    steam_data = get_steam_info(app_id)
    file_url_200 = check_file_status(app_id) 
    
    embed = nextcord.Embed(
        title=f"🔎 ข้อมูล Steam App ID: {app_id}",
        color=0x00FF00 if file_url_200 else 0xFF0000
    )
    
    if steam_data:
        embed.add_field(name="ชื่อแอป", value=steam_data['name'], inline=False)
        if 'developer' in steam_data and steam_data['developer'] != 'ไม่ระบุ':
            embed.add_field(name="ผู้พัฒนา", value=steam_data['developer'], inline=False)
        # แสดง DLC ตามฟอร์แมตใหม่ที่มึงขอ
        if 'dlc_count' in steam_data:
            embed.add_field(
                name="📦 DLCs ทั้งหมด",
                value=f"({steam_data['dlc_count']} รายการ)\n✅ พบ {steam_data.get('included_dlc', 0)} รายการ\n❌ สูญหาย {steam_data.get('missing_dlc', 0)} รายการ",
                inline=False
            )
        else:
            embed.add_field(name="DLCs ทั้งหมด", value=f"พบ **{steam_data['dlc_count']}** รายการ", inline=True)
        embed.add_field(name="วันวางจำหน่าย", value=steam_data['release_date'], inline=False)
        links_value = f"[Steam Store](https://store.steampowered.com/app/{app_id}/) | [SteamDB](https://steamdb.info/app/{app_id}/)"
        if steam_data['has_denuvo']:
            links_value += "\n:warning: ตรวจพบการป้องกัน Denuvo"
        embed.add_field(
            name="Links", 
            value=links_value, 
            inline=False
        )
        
        if steam_data['image']:
            embed.set_image(url=steam_data['image'])
            embed.set_footer(text="discord • DEV/g0d • Morrenus")
    else:
        embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
        embed.set_footer(text="discord • DEV/g0d • Morrenus")
        
    if file_url_200:
        embed.add_field(
            name="", 
            value=f"**📦 สถานะ:** ✅ [**พร้อมดาวน์โหลด↗**]({file_url_200})", 
            inline=False
        )
    else:
        embed.add_field(
            name="📦 สถานะ: ❌ ไม่พบไฟล์", 
            value="", 
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.slash_command(name="check_lua", description="ดึงไฟล์ .lua จาก App ID")
async def check_lua(interaction: nextcord.Interaction, app_id: str = nextcord.SlashOption(
    name="appid",
    description="ใส่ App ID (เช่น 2947440)",
    required=True
)):
    if interaction.channel_id not in ALLOWED_CHANNEL_IDS:
        await interaction.response.send_message("ไม่มีสิทธิในการใช้งาน กรุณาใช้คำสั่งที่ <#1422199765818413116>", ephemeral=True)
        return

    if not app_id.isdigit():
        await interaction.response.send_message("App ID ต้องเป็นตัวเลขเท่านั้น!", ephemeral=True)
        return

    await interaction.response.defer()  # แสดงว่ากำลังประมวลผล

    # ดึงข้อมูล Steam
    steam_data = get_steam_info(app_id)
    
    # ดาวน์โหลดและแตกไฟล์ ZIP จาก final URL
    lua_file_name, lua_file_path = download_and_extract_lua(app_id)

    embed = nextcord.Embed(
        title=f"🔎 ผลการค้นหาไฟล์ .lua สำหรับ App ID: {app_id}",
        color=0x00FF00 if lua_file_path else 0xFF0000
    )

    if steam_data:
        embed.add_field(name="ชื่อแอป", value=steam_data['name'], inline=False)
        embed.add_field(name="DLCs ทั้งหมด", value=f"พบ **{steam_data['dlc_count']}** รายการ", inline=True)
        if steam_data['has_denuvo']:
            embed.add_field(name="⚠️ Denuvo", value="ตรวจพบการป้องกัน Denuvo", inline=True)
        
        if steam_data['image']:
            embed.set_image(url=steam_data['image'])
            embed.set_footer(text="discord • DEV/g0d • Morrenus")
    else:
        embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
        embed.set_footer(text="discord • DEV/g0d • Morrenus")

    if lua_file_path and lua_file_name:
        embed.add_field(
            name="📄 สถานะไฟล์ .lua", 
            value=f"✅ พบไฟล์ **{lua_file_name}** และพร้อมส่ง!", 
            inline=False
        )
        # ส่งไฟล์ .lua
        file = nextcord.File(lua_file_path, filename=lua_file_name)
        await interaction.followup.send(embed=embed, file=file)
        # ลบไฟล์ชั่วคราวหลังจากส่ง
        os.remove(lua_file_path)
    else:
        embed.add_field(
            name="📄 สถานะไฟล์ .lua", 
            value="❌ ไม่พบไฟล์ .lua หรือเกิดข้อผิดพลาดในการดาวน์โหลด/แตกไฟล์", 
            inline=False
        )
        await interaction.followup.send(embed=embed)

@bot.slash_command(name="check_file", description="ตรวจสอบรายชื่อไฟล์ใน ZIP จาก App ID")
async def check_file(interaction: nextcord.Interaction, app_id: str = nextcord.SlashOption(
    name="appid",
    description="ใส่ App ID (เช่น 2947440)",
    required=True
)):
    if interaction.channel_id not in ALLOWED_CHANNEL_IDS:
        await interaction.response.send_message("ไม่มีสิทธิในการใช้งาน กรุณาใช้คำสั่งที่ <#1422199765818413116>", ephemeral=True)
        return

    if not app_id.isdigit():
        await interaction.response.send_message("App ID ต้องเป็นตัวเลขเท่านั้น!", ephemeral=True)
        return

    await interaction.response.defer()  # แสดงว่ากำลังประมวลผล

    # ดึงข้อมูล Steam
    steam_data = get_steam_info(app_id)
    
    # ดึงรายชื่อไฟล์ใน ZIP
    file_list = list_files_in_zip(app_id)

    embed = nextcord.Embed(
        title=f"🔎 รายชื่อไฟล์ใน ZIP สำหรับ App ID: {app_id}",
        color=0x00FF00 if file_list else 0xFF0000
    )

    if steam_data:
        embed.add_field(name="ชื่อแอป", value=steam_data['name'], inline=False)
        embed.add_field(name="DLCs ทั้งหมด", value=f"พบ **{steam_data['dlc_count']}** รายการ", inline=True)
        if steam_data['has_denuvo']:
            embed.add_field(name="⚠️ Denuvo", value="ตรวจพบการป้องกัน Denuvo", inline=True)
        
        if steam_data['image']:
            embed.set_image(url=steam_data['image'])
            embed.set_footer(text="discord • DEV/g0d • Morrenus")
    else:
        embed.add_field(name="สถานะ Steam", value="ไม่พบข้อมูลเกมบน Steam", inline=False)
        embed.set_footer(text="discord • DEV/g0d • Morrenus")

    if file_list:
        # แปลงรายชื่อไฟล์เป็นสตริง โดยเพิ่ม • นำหน้าแต่ละไฟล์
        file_list_str = "\n".join([f"• {file}" for file in file_list])
        embed.add_field(
            name="📄 รายชื่อไฟล์ใน ZIP", 
            value=f"✅ พบ **{len(file_list)}** ไฟล์\n{file_list_str}", 
            inline=False
        )
    else:
        embed.add_field(
            name="📄 รายชื่อไฟล์ใน ZIP", 
            value="❌ ไม่พบไฟล์ ZIP หรือเกิดข้อผิดพลาดในการดาวน์โหลด/แตกไฟล์", 
            inline=False
        )

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
