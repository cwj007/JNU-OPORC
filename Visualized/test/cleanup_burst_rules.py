import sqlite3
import os
from pathlib import Path

# 获取数据库路径
VISUALIZED_DIR = Path(__file__).parent.parent
CACHE_DIR = VISUALIZED_DIR / "cache"
HOTSEARCH_DB_PATH = CACHE_DIR / "hotsearch.db"

def cleanup_rules():
    if not HOTSEARCH_DB_PATH.exists():
        print(f"Database not found at {HOTSEARCH_DB_PATH}")
        return

    try:
        conn = sqlite3.connect(HOTSEARCH_DB_PATH)
        cur = conn.cursor()
        
        # 1. 删除所有“单贴高危负面预警”规则
        print("Deleting '单贴高危负面预警' rules...")
        cur.execute("DELETE FROM alert_rules WHERE name = '单贴高危负面预警'")
        deleted_burst = cur.rowcount
        print(f"Deleted {deleted_burst} '单贴高危负面预警' rules.")
        
        # 2. 删除对应的预警记录（可选，但为了保持干净可以做）
        # 这里只删除标题匹配的
        cur.execute("DELETE FROM alerts WHERE title LIKE '【单贴高危预警】%'")
        deleted_alerts = cur.rowcount
        print(f"Deleted {deleted_alerts} alert records starting with '【单贴高危预警】'.")
        
        conn.commit()
        conn.close()
        print("Cleanup completed successfully.")
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    cleanup_rules()
