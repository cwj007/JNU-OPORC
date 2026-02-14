import sqlite3
from pathlib import Path
from collections import Counter

# Config
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "Transformers" / "cache" / "processed_ids.db"

def verify():
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=== Database Date Distribution Verification ===\n")

    # 1. 检查 sync_date 的分布情况（入库日期）
    print("--- Distribution by sync_date (Entry Date) ---")
    cursor.execute("SELECT sync_date, COUNT(*) FROM processed_items GROUP BY sync_date ORDER BY sync_date DESC")
    sync_rows = cursor.fetchall()
    if sync_rows:
        for date, count in sync_rows:
            print(f"Date: {date} | Count: {count}")
    else:
        print("No data found in processed_items.")

    # 2. 检查 data_date 的分布情况（原始数据发布日期）
    print("\n--- Distribution by data_date (Original Creation Date) ---")
    cursor.execute("SELECT data_date, COUNT(*) FROM processed_items GROUP BY data_date ORDER BY data_date DESC LIMIT 10")
    data_rows = cursor.fetchall()
    if data_rows:
        for date, count in data_rows:
            print(f"Date: {date} | Count: {count}")
        print("... (showing top 10)")
    
    # 3. 随机抽取几条记录检查 sync_date 是否真的对应到了文件日期
    print("\n--- Sample Record Check ---")
    cursor.execute("SELECT unique_id, sync_date, created_at, source FROM processed_items LIMIT 5")
    samples = cursor.fetchall()
    for uid, s_date, c_at, src in samples:
        print(f"ID: {uid} | Sync Date: {s_date} | Created At: {c_at} | Source: {src}")

    # 4. 统计总数
    cursor.execute("SELECT COUNT(*) FROM processed_items")
    total = cursor.fetchone()[0]
    print(f"\nTotal Records in processed_items: {total}")

    conn.close()

if __name__ == "__main__":
    verify()
