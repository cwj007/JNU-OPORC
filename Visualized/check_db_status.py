import sqlite3
import os
from pathlib import Path

# 定义路径
VISUALIZED_DIR = Path(r"e:\JNU-OPORC\Visualized")
CACHE_DIR = VISUALIZED_DIR / "cache"
DB_PATH = CACHE_DIR / "hotsearch.db"

def check_data():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    print("Checking specific platforms (thepaper, toutiao)...")
    cur.execute("SELECT platform, title, rank, previous_rank, trend, hot_value, fetch_time FROM hot_search_data WHERE platform IN ('thepaper', 'toutiao') ORDER BY fetch_time DESC LIMIT 10")
    rows = cur.fetchall()
    
    print(f"{'Platform':<15} | {'Title':<20} | {'Rank':<4} | {'Prev':<4} | {'Trend':<5} | {'Hot':<10} | {'FetchTime'}")
    print("-" * 100)
    for r in rows:
        print(f"{r[0]:<15} | {str(r[1])[:20]:<20} | {r[2]:<4} | {str(r[3]):<4} | {r[4]:<5} | {str(r[5]):<10} | {r[6]}")
    
    # Check distinct platforms
    print("\nDistinct platforms in DB:")
    cur.execute("SELECT DISTINCT platform FROM hot_search_data")
    platforms = [r[0] for r in cur.fetchall()]
    print(platforms)
    
    # Check if there are any trends != 0
    cur.execute("SELECT COUNT(*) FROM hot_search_data WHERE trend != 0")
    trend_count = cur.fetchone()[0]
    print(f"\nTotal rows with trend != 0: {trend_count}")
    
    conn.close()

if __name__ == "__main__":
    check_data()
