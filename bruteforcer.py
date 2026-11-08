import os
import time
import requests
from bs4 import BeautifulSoup
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TARGET_URL_SITE = os.getenv("TARGET_URL_SITE", "https://example.com/search?q={cccd}")

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
    """Tạo kết nối mới đến Neon DB với cơ chế an toàn"""
    if not DATABASE_URL:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"[!] Lỗi kết nối DB: {e}")
        return None

def init_db():
    """Khởi tạo cấu trúc bảng chuẩn xác, cố định ID = 1 cho progress"""
    conn = get_db_connection()
    if not conn:
        print("[!] Không thể kết nối DB để khởi tạo.")
        return
    try:
        cur = conn.cursor()
        
        # Bảng lưu kết quả trúng
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scanned_records (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                class_name TEXT,
                cccd VARCHAR(12) UNIQUE NOT NULL,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Bảng lưu tiến độ với ID cố định = 1 để tránh lệch dòng
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
        
        # Đảm bảo luôn có đúng 1 bản ghi tiến độ gốc với id = 1
        cur.execute("SELECT COUNT(*) FROM scan_progress WHERE id = 1;")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO scan_progress (id, province, year, gender, current_seq) VALUES (1, %s, %s, %s, %s);",
                (TARGET_PROVINCES[0], YEARS[0], GENDERS[0], 0)
            )
            
        conn.commit()
        cur.close()
        conn.close()
        print("[i] Khởi tạo DB thành công!")
    except Exception as e:
        print(f"[!] Lỗi khởi tạo DB: {e}")

def get_db_progress():
    """Đọc tiến độ hiện tại từ DB"""
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
    except Exception as e:
        print(f"[!] Lỗi đọc tiến độ: {e}")
    return TARGET_PROVINCES[0], YEARS[0], GENDERS[0], 0

def save_db_progress(prov: str, year: str, gender: str, seq: int):
    """Lưu tiến độ liên tục với id = 1 cố định, tự động reconnect nếu lỗi kết nối"""
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
    except Exception as e:
        print(f"[!] Lỗi lưu tiến độ DB: {e}")

def save_to_neon(full_name: str, class_name: str, cccd: str):
    """Lưu thông tin tìm được vào bảng kết quả"""
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
    except Exception as e:
        print(f"[!] Lỗi ghi record DB: {e}")

def run_scanner():
    """Hàm chạy quét chính được bao bọc bởi lớp chống sập toàn cục"""
    init_db()
    
    while True:
        try:
            cur_prov, cur_year, cur_gender, cur_seq = get_db_progress()
            print(f"[i] Tiếp tục quét từ DB - Tỉnh: {cur_prov} | Năm: {cur_year} | Giới tính: {cur_gender} | Seq: {cur_seq}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SingleScanner"
            }

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
                            
                            # Cập nhật tiến độ liên tục vào DB
                            save_db_progress(prov, year, gender, seq)
                            
                            url = TARGET_URL_SITE.format(cccd=cccd)
                            
                            try:
                                response = requests.get(url, headers=headers, timeout=10)
                                response.raise_for_status()
                                
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
                                            print(f"[+] Tìm thấy! CCCD: {cccd} -> Họ tên: {full_name} | Lớp: {class_name}")
                                            break
                                            
                            except requests.exceptions.RequestException:
                                time.sleep(2)
                            
                            time.sleep(REQUEST_DELAY)

            print("[i] Đã hoàn thành toàn bộ dải quét trên toàn quốc! Đợi 60s rồi quét lại từ đầu...")
            time.sleep(60)
            
        except Exception as e:
            print(f"[!] Lỗi nghiêm trọng trong luồng quét: {e}. Tự động khôi phục sau 5 giây...")
            time.sleep(5)
