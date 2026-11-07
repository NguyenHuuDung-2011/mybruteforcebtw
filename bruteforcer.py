import os
import time
import requests
from bs4 import BeautifulSoup
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TARGET_URL_TEMPLATE = os.getenv("TARGET_URL_TEMPLATE", "https://example.com/search?q={cccd}")

# Danh sách 63 tỉnh/thành phố chuẩn (chỉ giữ mã số)
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

TARGET_PROVINCES = PROVINCES   # Tỉnh cần quét (Ví dụ: TP.HCM)
YEARS = ["09", "10", "11"]   # Đã bổ sung năm sinh 2009, 2010 và 2011
GENDERS = ["2", "3"]          # Giới tính

HARDCODE_MAX_LIMIT = 80000    # Mốc trần hardcode
REQUEST_DELAY = 0.3           
PROGRESS_FILE = "progress.txt"

def init_db():
    """Tự động tạo bảng trên Neon DB nếu chưa tồn tại"""
    if not DATABASE_URL:
        print("[!] Lỗi: DATABASE_URL chưa được cấu hình trong .env")
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scraped_records (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                class_name TEXT,
                cccd VARCHAR(12) UNIQUE NOT NULL,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("[i] Đã kiểm tra và khởi tạo bảng thành công trên Neon DB!")
    except Exception as e:
        print(f"[!] Lỗi khởi tạo DB: {e}")

def save_to_neon(full_name: str, class_name: str, cccd: str):
    if not DATABASE_URL:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO scraped_records (full_name, class_name, cccd) VALUES (%s, %s, %s) ON CONFLICT (cccd) DO NOTHING;",
            (full_name, class_name, cccd)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[!] Lỗi ghi DB: {e}")

def get_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip().split(",")
            if len(content) == 4 and content[3].isdigit():
                return content[0], content[1], content[2], int(content[3])
    return TARGET_PROVINCES[0], YEARS[0], GENDERS[0], 0

def save_progress(prov: str, year: str, gender: str, seq: int):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        f.write(f"{prov},{year},{gender},{seq}")

def run_scanner():
    # Tự động tạo bảng ngay khi chạy worker
    init_db()
    
    cur_prov, cur_year, cur_gender, cur_seq = get_progress()
    print(f"[i] Bắt đầu quét từ Tỉnh: {cur_prov} | Năm: {cur_year} | Giới tính: {cur_gender} | Seq: {cur_seq}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SingleScanner"
    }

    prov_idx = TARGET_PROVINCES.index(cur_prov) if cur_prov in TARGET_PROVINCES else 0

    for p_i in range(prov_idx, len(TARGET_PROVINCES)):
        prov = TARGET_PROVINCES[p_i]
        
        year_idx = YEARS.index(cur_year) if (prov == cur_prov and cur_year in YEARS) else 0
        for y_i in range(year_idx if p_i == prov_idx else 0, len(YEARS)):
            year = YEARS[y_i]
            
            gender_idx = GENDERS.index(cur_gender) if (prov == cur_prov and year == cur_year and cur_gender in GENDERS) else 0
            for g_i in range(gender_idx if (p_i == prov_idx and y_i == year_idx) else 0, len(GENDERS)):
                gender = GENDERS[g_i]
                
                prefix = f"{prov}{gender}{year}"
                seq_start = cur_seq if (prov == cur_prov and year == cur_year and gender == cur_gender) else 0
                cur_seq = 0 

                for seq in range(seq_start, HARDCODE_MAX_LIMIT + 1):
                    cccd = f"{prefix}{seq:06d}"
                    save_progress(prov, year, gender, seq)
                    
                    url = TARGET_URL_TEMPLATE.format(cccd=cccd)
                    
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

    print("[i] Đã hoàn thành toàn bộ dải quét cho các năm 09, 10, 11!")