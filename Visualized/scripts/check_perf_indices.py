import sqlite3
import os
from pathlib import Path

# 使用相对路径定义数据库路径
# 脚本位于 Visualized/scripts/，根目录是 e:/JNU-OPORC
ROOT_DIR = Path(__file__).parent.parent.parent

HOTSEARCH_DB_PATH = ROOT_DIR / 'Visualized' / 'cache' / 'hotsearch.db'
TRANSFORMERS_DB_PATH = ROOT_DIR / 'Transformers' / 'cache' / 'processed_ids.db'
MEDIA_CRAWLER_DB_PATH = ROOT_DIR / 'MediaCrawler' / 'database' / 'sqlite_tables.db'

def enable_wal(db_path):
    """为数据库开启 WAL 模式以提高并发性能"""
    if not db_path.exists():
        print(f"数据库未找到: {db_path}")
        return
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.close()
        print(f"已为 {db_path.name} 开启 WAL 模式")
    except Exception as e:
        print(f"为 {db_path.name} 开启 WAL 模式失败: {e}")

def add_indices():
    """添加性能优化所需的索引"""
    # 1. hotsearch.db 索引
    if HOTSEARCH_DB_PATH.exists():
        conn = sqlite3.connect(HOTSEARCH_DB_PATH)
        cur = conn.cursor()
        print(f"正在为 {HOTSEARCH_DB_PATH.name} 添加索引...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hotsearch_platform_fetch ON hot_search_data(platform, fetch_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hotsearch_fetch_time ON hot_search_data(fetch_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
        conn.commit()
        conn.close()

    # 2. processed_ids.db (Transformers) 索引
    if TRANSFORMERS_DB_PATH.exists():
        conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
        cur = conn.cursor()
        print(f"正在为 {TRANSFORMERS_DB_PATH.name} 添加索引...")
        # content 表
        cur.execute("CREATE INDEX IF NOT EXISTS idx_content_created_at ON content(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_content_source ON content(source)")
        # comments 表
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_created_at ON comments(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_source ON comments(source)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_sentiment ON comments(sentiment)")
        conn.commit()
        conn.close()
        
    # 3. sqlite_tables.db (MediaCrawler) 索引
    if MEDIA_CRAWLER_DB_PATH.exists():
        conn = sqlite3.connect(MEDIA_CRAWLER_DB_PATH)
        cur = conn.cursor()
        print(f"正在为 {MEDIA_CRAWLER_DB_PATH.name} 添加索引...")
        # 为常用查询字段添加索引，例如 user_id 或 note_id
        # 这里假设了一些常见的表名，实际根据数据库结构调整
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_weibo_creator_id ON weibo_creator(user_id)")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()

if __name__ == "__main__":
    for db in [HOTSEARCH_DB_PATH, TRANSFORMERS_DB_PATH, MEDIA_CRAWLER_DB_PATH]:
        enable_wal(db)
    add_indices()
    print("索引管理完成。")
