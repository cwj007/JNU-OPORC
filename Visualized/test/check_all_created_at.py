import sqlite3
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(r"e:\JNU-OPORC")
TRANSFORMERS_DB = BASE_DIR / "Transformers" / "cache" / "processed_ids.db"
MEDIA_CRAWLER_DB = BASE_DIR / "MediaCrawler" / "database" / "sqlite_tables.db"

today = datetime.now().strftime("%Y-%m-%d")
print(f"--- Checking for records with created_at starting with {today} ---")

def check_transformers():
    print(f"\n[Transformers DB: {TRANSFORMERS_DB}]")
    if not TRANSFORMERS_DB.exists():
        print("File not found")
        return
    conn = sqlite3.connect(TRANSFORMERS_DB)
    cursor = conn.cursor()
    
    # Content
    cursor.execute("SELECT count(*) FROM content WHERE created_at LIKE ?", (f"{today}%",))
    print(f"  - Content created today: {cursor.fetchone()[0]}")
    
    # Comments
    cursor.execute("SELECT count(*) FROM comments WHERE created_at LIKE ?", (f"{today}%",))
    print(f"  - Comments created today: {cursor.fetchone()[0]}")
    
    # Distinct dates in content
    cursor.execute("SELECT DISTINCT SUBSTR(created_at, 1, 10) as d FROM content ORDER BY d DESC LIMIT 5")
    dates = [row[0] for row in cursor.fetchall()]
    print(f"  - Recent content publish dates: {dates}")
    
    conn.close()

def check_mediacrawler():
    print(f"\n[MediaCrawler DB: {MEDIA_CRAWLER_DB}]")
    if not MEDIA_CRAWLER_DB.exists():
        print("File not found")
        return
    conn = sqlite3.connect(MEDIA_CRAWLER_DB)
    cursor = conn.cursor()
    
    # List all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    for table in tables:
        # Check if table has created_at column
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'create_at' in columns:
            cursor.execute(f"SELECT count(*) FROM {table} WHERE create_at >= ?", (int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000),))
            count = cursor.fetchone()[0]
            if count > 0:
                print(f"  - {table} (create_at timestamp): {count}")
        elif 'created_at' in columns:
            cursor.execute(f"SELECT count(*) FROM {table} WHERE created_at LIKE ?", (f"{today}%",))
            count = cursor.fetchone()[0]
            if count > 0:
                print(f"  - {table} (created_at string): {count}")
    
    conn.close()

if __name__ == "__main__":
    check_transformers()
    check_mediacrawler()
