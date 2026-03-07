import sqlite3
import datetime
from pathlib import Path

# 定义数据库路径
PROCESSED_DB = Path(r"e:\JNU-OPORC\Transformers\cache\processed_ids.db")
HOTSEARCH_DB = Path(r"e:\JNU-OPORC\Visualized\cache\hotsearch.db")
MC_DB = Path(r"e:\JNU-OPORC\MediaCrawler\database\sqlite_tables.db")

now = datetime.datetime.now()
twenty_four_hours_ago = now - datetime.timedelta(hours=24)
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

def check_db(db_path, table_name, time_col, date_format="%Y-%m-%d %H:%M:%S"):
    print(f"\n--- Checking {db_path.name} (table: {table_name}) ---")
    if not db_path.exists():
        print(f"Database file not found: {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # 检查表是否存在
        cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not cur.fetchone():
            print(f"Table '{table_name}' not found.")
            return

        # 获取最新的一条数据时间
        cur.execute(f"SELECT {time_col} FROM {table_name} ORDER BY {time_col} DESC LIMIT 1")
        latest = cur.fetchone()
        if latest:
            print(f"Latest record time: {latest[0]}")
        else:
            print("No records found in table.")
            return

        # 统计今日数据量
        cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {time_col} >= ?", (today_start.strftime(date_format),))
        today_count = cur.fetchone()[0]
        print(f"Today's records (since {today_start.strftime(date_format)}): {today_count}")

        # 统计24小时内数据量
        cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {time_col} >= ?", (twenty_four_hours_ago.strftime(date_format),))
        twenty_four_count = cur.fetchone()[0]
        print(f"Last 24h records (since {twenty_four_hours_ago.strftime(date_format)}): {twenty_four_count}")

        conn.close()
    except Exception as e:
        print(f"Error checking {db_path.name}: {e}")

# 1. 检查 Transformers 处理后的舆情数据
check_db(PROCESSED_DB, "content", "created_at")

# 2. 检查 MediaCrawler 原始微博数据 (使用 create_date_time 字段)
check_db(MC_DB, "weibo_note", "create_date_time")

# 3. 检查热搜数据 (fetch_time 字段)
check_db(HOTSEARCH_DB, "hot_search_data", "fetch_time")
