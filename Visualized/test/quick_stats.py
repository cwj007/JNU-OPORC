
import sqlite3
import os
import json
from pathlib import Path

# Paths
BASE_DIR = Path(r"e:\JNU-OPORC")
HOTSEARCH_DB = BASE_DIR / "Visualized" / "cache" / "hotsearch.db"
TRANSFORMERS_DB = BASE_DIR / "Transformers" / "cache" / "processed_ids.db"
MEDIA_CRAWLER_DB = BASE_DIR / "MediaCrawler" / "database" / "sqlite_tables.db"
CACHE_JSON = BASE_DIR / "Transformers" / "cache" / "analysis_cache.json"

def get_count(db_path, table_name):
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        return f"Error: {e}"

def get_stats():
    print("--- Detailed System Data Metrics ---")
    
    # 1. Platform Data (MediaCrawler)
    print(f"\n[MediaCrawler Storage]")
    print(f"  - Weibo Creators: {get_count(MEDIA_CRAWLER_DB, 'weibo_creator')}")
    print(f"  - Zhihu Creators: {get_count(MEDIA_CRAWLER_DB, 'zhihu_creator')}")
    
    # 2. Processed Content (Transformers)
    print(f"\n[Transformers AI Analysis]")
    print(f"  - Total Articles/Notes: {get_count(TRANSFORMERS_DB, 'content')}")
    print(f"  - Total Comments: {get_count(TRANSFORMERS_DB, 'comments')}")
    print(f"  - Top Topics Identified: {get_count(TRANSFORMERS_DB, 'top_topics')}")
    
    # 3. Monitoring & Alerts (Visualized)
    print(f"\n[Visualized Monitoring]")
    print(f"  - Hot Search Records: {get_count(HOTSEARCH_DB, 'hot_search_data')}")
    print(f"  - System Alerts Triggered: {get_count(HOTSEARCH_DB, 'alerts')}")
    print(f"  - Monitoring Tasks: {get_count(HOTSEARCH_DB, 'monitoring_tasks')}")
    
    # 4. AI Cache
    cache_count = 0
    if CACHE_JSON.exists():
        with open(CACHE_JSON, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
            cache_count = len(cache_data.get("analysis", {}))
    print(f"\n[AI Performance Cache]")
    print(f"  - Multimodal Analysis Cache: {cache_count} entries")

    # 5. Sample Sentiment Data (from DB)
    if TRANSFORMERS_DB.exists():
        conn = sqlite3.connect(TRANSFORMERS_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT sentiment, COUNT(*) FROM comments GROUP BY sentiment")
        dist = cursor.fetchall()
        print(f"\n[Sentiment Distribution (Sample)]")
        for s, c in dist:
            print(f"  - {s}: {c}")
        conn.close()

if __name__ == "__main__":
    get_stats()
