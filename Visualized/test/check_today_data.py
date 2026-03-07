import sqlite3
import datetime
from pathlib import Path

# 修正数据库路径
# content 表在 e:\JNU-OPORC\Transformers\cache\processed_ids.db
DB_PATH = Path(r"e:\JNU-OPORC\Transformers\cache\processed_ids.db")

def check_data():
    if not DB_PATH.exists():
        print(f"Error: Database file not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    print(f"Inspecting table 'content' in {DB_PATH}")
    
    # 检查是否有任何 2026-03-07 的数据
    print("\nChecking for any data on 2026-03-07:")
    cur.execute("SELECT created_at FROM content WHERE created_at LIKE '2026-03-07%'")
    rows = cur.fetchall()
    print(f"Found {len(rows)} records for 2026-03-07")
    for row in rows[:5]:
        print(row[0])

    # 检查是否有任何 2026-03-06 的数据 (确认昨天有数据)
    print("\nChecking for any data on 2026-03-06:")
    cur.execute("SELECT COUNT(*) FROM content WHERE created_at LIKE '2026-03-06%'")
    count_06 = cur.fetchone()[0]
    print(f"Found {count_06} records for 2026-03-06")

    conn.close()

if __name__ == "__main__":
    check_data()
