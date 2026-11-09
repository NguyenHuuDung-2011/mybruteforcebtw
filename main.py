import os
import subprocess
import sys
from flask import Flask, render_template
import psycopg2
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

# Tự động khởi chạy worker.py độc lập ngay khi Flask boot (chỉ chạy 1 lần duy nhất)
lock_file = "/tmp/scanner_started.lock"
if not os.path.exists(lock_file):
    try:
        with open(lock_file, "w") as f:
            f.write("locked")
        subprocess.Popen([sys.executable, "worker.py"])
        print("[i] Đã khởi chạy tiến trình quét ngầm độc lập (worker.py) thành công!")
    except Exception as e:
        print(f"[!] Không thể khởi chạy worker: {e}")

def get_all_records():
    if not DATABASE_URL:
        return []
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT full_name, class_name, cccd, scanned_at FROM scanned_records ORDER BY id DESC;")
        records = cur.fetchall()
        cur.close()
        conn.close()
        return records
    except:
        return []

@app.route("/")
def index():
    records = get_all_records()
    return render_template("index.html", records=records)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
