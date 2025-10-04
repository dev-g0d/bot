import requests
import uuid
import time
import sqlite3
import os
from flask import Flask, Response, request, stream_with_context, redirect, url_for

app = Flask(__name__)

# กำหนดที่อยู่ของฐานข้อมูล SQLite
DB_PATH = os.path.join(os.path.dirname(__file__), 'tokens.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            expiry_time REAL NOT NULL,
            used INTEGER NOT NULL,
            file_id TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

init_db()

TARGET_URL_BASE = 'https://mellyiscoolaf.pythonanywhere.com/m/'

@app.route('/app_request/<file_id>')
def app_request(file_id):
    """
    URL สำหรับการขอ token โดยผู้ใช้ต้องระบุ file_id
    ตัวอย่าง: https://devg0d.pythonanywhere.com/app_request/2947440
    """
    token = str(uuid.uuid4())
    expiry_time = time.time() + 3600  # Token มีอายุ 60 วินาที

    conn = get_db_connection()
    conn.execute('INSERT INTO tokens (token, expiry_time, used, file_id) VALUES (?, ?, ?, ?)', (token, expiry_time, 0, file_id))
    conn.commit()
    conn.close()

    # Redirect ไปยัง URL ที่มีเพียง token เท่านั้น
    return redirect(url_for('proxy', token=token))

@app.route('/app/<token>')
def proxy(token):
    """
    URL ที่มีการป้องกันด้วย token โดยตัว token จะบอกว่าควรดึงไฟล์อะไร
    ตัวอย่าง: https://devg0d.pythonanywhere.com/app/12345678-abcd-1234-abcd-1234567890ab
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tokens WHERE token = ?', (token,))
    token_data = cursor.fetchone()

    if not token_data:
        conn.close()
        return "Invalid or expired token.", 403

    if time.time() > token_data['expiry_time']:
        conn.execute('DELETE FROM tokens WHERE token = ?', (token,))
        conn.commit()
        conn.close()
        return "Invalid or expired token.", 403

    # if token_data['used']:
    #    conn.close()
    #    return "This token has already been used.", 403

    # ทำเครื่องหมายว่า token ถูกใช้แล้ว
    # conn.execute('UPDATE tokens SET used = 1 WHERE token = ?', (token,))
    # conn.commit()

    # ดึง file_id จากข้อมูลใน token
    file_id = token_data['file_id']
    conn.close()

    # ดึงข้อมูลจากเซิร์ฟเวอร์ปลายทาง
    target_url = TARGET_URL_BASE + file_id
    proxy_headers = dict(request.headers)
    if 'Host' in proxy_headers:
        del proxy_headers['Host']

    try:
        resp = requests.get(target_url, stream=True, headers=proxy_headers)
        response = Response(stream_with_context(resp.iter_content(chunk_size=1024)),
                            status=resp.status_code)
        for key, value in resp.headers.items():
            if key.lower() not in ('content-encoding', 'content-length', 'transfer-encoding'):
                response.headers[key] = value
        return response

    except requests.exceptions.RequestException as e:
        return f"Error fetching content: {e}", 500
