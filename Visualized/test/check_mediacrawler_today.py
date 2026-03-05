import sqlite3
import time
from datetime import datetime

db = r'e:\JNU-OPORC\MediaCrawler\database\sqlite_tables.db'
conn = sqlite3.connect(db)
cursor = conn.cursor()

# Get timestamp for start of today (ms)
today_start_ts = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
today_str = datetime.now().strftime("%Y-%m-%d")

print(f"Checking for records added since: {datetime.fromtimestamp(today_start_ts/1000)}")

tables = ['weibo_note', 'weibo_note_comment', 'zhihu_content', 'zhihu_comment']

for table in tables:
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [col[1] for col in cursor.fetchall()]
    
    # 1. Check add_ts (added to DB time)
    if 'add_ts' in cols:
        cursor.execute(f"SELECT count(*) FROM {table} WHERE add_ts >= ?", (today_start_ts,))
        added_count = cursor.fetchone()[0]
        print(f"Table {table}: {added_count} records added today (add_ts)")

    # 2. Check publish time (create_time or create_date_time or created_time)
    pub_col = None
    if 'create_date_time' in cols: pub_col = 'create_date_time'
    elif 'create_time' in cols: pub_col = 'create_time'
    elif 'created_time' in cols: pub_col = 'created_time'
    elif 'publish_time' in cols: pub_col = 'publish_time'
    
    if pub_col:
        cursor.execute(f"SELECT count(*) FROM {table} WHERE {pub_col} LIKE ?", (f"{today_str}%",))
        pub_count = cursor.fetchone()[0]
        print(f"Table {table}: {pub_count} records published today ({pub_col})")

conn.close()
