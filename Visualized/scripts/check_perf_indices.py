import sqlite3
import os
from pathlib import Path

# Paths to databases
HOTSEARCH_DB_PATH = Path(r'e:\JNU-OPORC\Visualized\cache\hotsearch.db')
TRANSFORMERS_DB_PATH = Path(r'e:\JNU-OPORC\Transformers\cache\processed_ids.db')
MEDIA_CRAWLER_DB_PATH = Path(r'e:\JNU-OPORC\MediaCrawler\database\sqlite_tables.db')

def enable_wal(db_path):
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.close()
        print(f"WAL mode enabled for {db_path}")
    except Exception as e:
        print(f"Error enabling WAL for {db_path}: {e}")

def add_indices():
    # 1. hotsearch.db indices
    if HOTSEARCH_DB_PATH.exists():
        conn = sqlite3.connect(HOTSEARCH_DB_PATH)
        cur = conn.cursor()
        print(f"Adding indices to {HOTSEARCH_DB_PATH}...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hotsearch_platform_fetch ON hot_search_data(platform, fetch_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hotsearch_fetch_time ON hot_search_data(fetch_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
        conn.commit()
        conn.close()

    # 2. processed_ids.db (Transformers) indices
    if TRANSFORMERS_DB_PATH.exists():
        conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
        cur = conn.cursor()
        print(f"Adding indices to {TRANSFORMERS_DB_PATH}...")
        # content table
        cur.execute("CREATE INDEX IF NOT EXISTS idx_content_created_at ON content(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_content_source ON content(source)")
        # comments table
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_created_at ON comments(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_source ON comments(source)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_sentiment ON comments(sentiment)")
        conn.commit()
        conn.close()

if __name__ == "__main__":
    for db in [HOTSEARCH_DB_PATH, TRANSFORMERS_DB_PATH, MEDIA_CRAWLER_DB_PATH]:
        enable_wal(db)
    add_indices()
