import os
import threading
from flask import Flask, render_template
import psycopg2
from dotenv import load_dotenv
from bruteforcer import run_scanner, init_db, get_db_connection

load_dotenv()

app = Flask(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

# Khởi tạo bảng ngay khi module được load
init_db()

def get_all_records():
    """Lấy danh sách bản ghi đã tìm được hiển thị lên web"""
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT full_name, class_name, cccd, scanned_at FROM scanned_records ORDER BY id DESC;")
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
    scanner_thread = threading.Thread(target=run_scanner, daemon=True)
    scanner_thread.start()

# Kích hoạt luồng chạy ngầm ngay khi app boot
start_background_scanner()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
