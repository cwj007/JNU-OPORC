import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime

# Config
BASE_DIR = Path(__file__).parent.parent
LABELED_DATA_FILE = BASE_DIR / "Transformers" / "output" / "labeled_results.jsonl"
DB_PATH = BASE_DIR / "Transformers" / "cache" / "processed_ids.db"

def sync():
    if not LABELED_DATA_FILE.exists():
        print(f"Source file {LABELED_DATA_FILE} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 重新创建表，包含 ip_location
    cursor.execute("DROP TABLE IF EXISTS processed_items")
    cursor.execute('''
        CREATE TABLE processed_items (
            unique_id TEXT PRIMARY KEY,
            note_id TEXT,
            comment_id TEXT,
            data_date TEXT,
            sentiment TEXT,
            intent TEXT,
            keywords TEXT,
            ip_location TEXT
        )
    ''')
    
    print(f"Reading from {LABELED_DATA_FILE}...")
    db_entries = []
    with open(LABELED_DATA_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line)
                note_id = str(item.get('note_id'))
                comment_id = str(item.get('comment_id', '0'))
                unique_id = f"{note_id}_{comment_id}"
                
                # 提取日期
                created_at = item.get('created_at', '')
                data_date = ""
                if created_at:
                    try:
                        dt_str = created_at.split(' ')[0]
                        datetime.strptime(dt_str, "%Y-%m-%d")
                        data_date = dt_str
                    except:
                        data_date = item.get('data_date', '')
                
                sentiment = str(item.get("sentiment_analysis", {}).get("sentiment", "Unknown"))
                intent = str(item.get("sentiment_analysis", {}).get("intent", "Unknown"))
                keywords = json.dumps(item.get("keywords", []), ensure_ascii=False)
                ip_location = str(item.get("ip_location", ""))
                
                db_entries.append((unique_id, note_id, comment_id, data_date, sentiment, intent, keywords, ip_location))
            except:
                continue

    print(f"Syncing {len(db_entries)} entries to database with IP Location...")
    cursor.executemany('''
        INSERT OR REPLACE INTO processed_items (unique_id, note_id, comment_id, data_date, sentiment, intent, keywords, ip_location) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', db_entries)
    
    conn.commit()
    conn.close()
    print("Sync complete.")

if __name__ == "__main__":
    sync()
