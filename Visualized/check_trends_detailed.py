import sqlite3
from pathlib import Path

# 定义路径
VISUALIZED_DIR = Path(r"e:\JNU-OPORC\Visualized")
CACHE_DIR = VISUALIZED_DIR / "cache"
DB_PATH = CACHE_DIR / "hotsearch.db"

def check_trends():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    print("Checking all platforms for non-zero trends...")
    cur.execute("SELECT platform, COUNT(*) as count FROM hot_search_data WHERE trend != 0 GROUP BY platform")
    rows = cur.fetchall()
    if not rows:
        print("No platforms have non-zero trends.")
    for r in rows:
        print(f"Platform: {r['platform']}, Count of trend != 0: {r['count']}")

    print("\nChecking latest 5 fetch times in DB:")
    cur.execute("SELECT DISTINCT fetch_time FROM hot_search_data ORDER BY fetch_time DESC LIMIT 5")
    times = [r[0] for r in cur.fetchall()]
    print(times)

    if times:
        latest_time = times[0]
        print(f"\nSample data from latest fetch ({latest_time}):")
        cur.execute("SELECT platform, title, rank, previous_rank, trend FROM hot_search_data WHERE fetch_time = ? LIMIT 10", (latest_time,))
        for r in cur.fetchall():
            print(f"{r['platform']:<15} | {r['title'][:30]:<30} | Rank: {r['rank']:<2} | Prev: {str(r['previous_rank']):<4} | Trend: {r['trend']}")

    conn.close()

if __name__ == "__main__":
    check_trends()
