import os
import threading
from flask import Flask, render_template
import psycopg
from dotenv import load_dotenv
from bruteforcer import run_scanner

load_dotenv()

app = Flask(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

def get_all_records():
    """Lấy danh sách dữ liệu đã scan từ Neon DB"""
    if not DATABASE_URL:
        return []
    try:
        conn = psycopg.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT full_name, cccd, scanned_at FROM scanned_records ORDER BY id DESC;")
        records = cur.fetchall()
        cur.close()
        conn.close()
        return records
    except Exception as e:
        print(f"[!] Lỗi truy vấn DB: {e}")
        return []

@app.route("/")
def index():
    records = get_all_records()
    return render_template("index.html", records=records)

def start_background_scanner():
    """Khởi chạy scraper ngầm trong một Background Thread riêng biệt"""
    scanner_thread = threading.Thread(target=run_scanner, daemon=True)
    scanner_thread.start()

if __name__ == "__main__":
    # Kích hoạt luồng quét ngầm ngay khi app khởi động
    start_background_scanner()
    
    # Chạy ứng dụng Flask
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)