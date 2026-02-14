import json
import sqlite3
import os
import re
from pathlib import Path
from datetime import datetime

# Config
BASE_DIR = Path(__file__).resolve().parent.parent
LABELED_DATA_FILE = BASE_DIR / "Transformers" / "output" / "labeled_results.jsonl"
HISTORY_DIR = BASE_DIR / "Transformers" / "output" / "history"
DB_PATH = BASE_DIR / "Transformers" / "cache" / "processed_ids.db"

def ensure_columns(cursor, table_name, required_columns_sql):
    """安全地确保表存在并拥有所有列，不删除原有数据"""
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} {required_columns_sql}")
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    cols_in_sql = re.findall(r'(\w+)\s+(?:TEXT|INTEGER|BOOLEAN|DATETIME)', required_columns_sql, re.IGNORECASE)
    for col in cols_in_sql:
        if col not in existing_cols:
            print(f"  Adding missing column {col} to table {table_name}...")
            col_type = "TEXT"
            if "count" in col.lower() or "id" in col.lower(): col_type = "INTEGER" if "id" not in col.lower() else "TEXT"
            if "detected" in col.lower(): col_type = "BOOLEAN"
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type}")
            except Exception as e:
                print(f"  Warning: Could not add column {col}: {e}")

def sync_history():
    print("Starting historical data recovery sync...")
    print(f"Database: {DB_PATH}")
    
    # Ensure directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cursor = conn.cursor()

    # 定义表结构
    processed_items_sql = '''(
        unique_id TEXT PRIMARY KEY, note_id TEXT, comment_id TEXT, top_id TEXT,
        data_date TEXT, sync_date TEXT, sync_time TEXT, created_at TEXT,
        content TEXT, sentiment TEXT, fine_grained_sentiment TEXT, intent TEXT,
        keywords TEXT, ip_location TEXT, visual_objects TEXT, ocr_text TEXT,
        author TEXT, source TEXT, liked_count INTEGER, comments_count INTEGER,
        shared_count INTEGER, gender TEXT, parent_comment_id TEXT
    )'''
    content_sql = '''(
        note_id TEXT PRIMARY KEY, title TEXT, content TEXT, author TEXT, source TEXT,
        url TEXT, created_at TEXT, ip_location TEXT, image_paths TEXT, video_path TEXT,
        liked_count INTEGER, comments_count INTEGER, shared_count INTEGER, collected_count INTEGER,
        sentiment TEXT, fine_grained_sentiment TEXT, intent TEXT, irony_detected BOOLEAN,
        reasoning TEXT, keywords TEXT, visual_objects TEXT, ocr_text TEXT, sync_date TEXT, sync_time TEXT
    )'''
    comments_sql = '''(
        comment_id TEXT PRIMARY KEY, note_id TEXT, content TEXT, author TEXT, source TEXT,
        url TEXT, created_at TEXT, ip_location TEXT, gender TEXT, parent_comment_id TEXT,
        comment_like_count INTEGER, sub_comment_count INTEGER, image_paths TEXT,
        sentiment TEXT, fine_grained_sentiment TEXT, intent TEXT, irony_detected BOOLEAN,
        reasoning TEXT, labels TEXT, keywords TEXT, visual_objects TEXT, ocr_text TEXT,
        sync_date TEXT, sync_time TEXT, FOREIGN KEY (note_id) REFERENCES content(note_id)
    )'''

    ensure_columns(cursor, "processed_items", processed_items_sql)
    ensure_columns(cursor, "content", content_sql)
    ensure_columns(cursor, "comments", comments_sql)

    # 收集所有待处理文件
    files_to_process = []
    if LABELED_DATA_FILE.exists():
        files_to_process.append(LABELED_DATA_FILE)
    if HISTORY_DIR.exists():
        files_to_process.extend(list(HISTORY_DIR.glob("labeled_results_*.jsonl")))

    print(f"Found {len(files_to_process)} files to process.")
    print(f"DEBUG: HISTORY_DIR = {HISTORY_DIR.resolve()}")
    if HISTORY_DIR.exists():
        print(f"DEBUG: HISTORY_DIR contents: {list(HISTORY_DIR.iterdir())}")
    else:
        print("DEBUG: HISTORY_DIR does not exist")

    total_synced = 0
    
    try:
        for file_path in files_to_process:
            print(f"Processing {file_path.name}...")
            
            # 核心逻辑：从文件名提取日期作为 sync_date 的基准
            file_date = ""
            if "_" in file_path.name:
                try:
                    parts = file_path.name.split("_")
                    for part in parts:
                        date_part = part.split(".")[0]
                        if len(date_part) == 10 and date_part.count("-") == 2:
                            datetime.strptime(date_part, "%Y-%m-%d")
                            file_date = date_part
                            break
                except: pass
            
            if not file_date:
                mtime = os.path.getmtime(file_path)
                file_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

            print(f"  Processing file date: {file_date}")

            batch_db = []
            batch_content = []
            batch_comments = []

            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        item = json.loads(line)
                        note_id = str(item.get('note_id', ''))
                        comment_id = str(item.get('comment_id', '0'))
                        if not note_id: continue
                        
                        unique_id = f"{note_id}_{comment_id}"
                        created_at = item.get('created_at', '')
                        
                        # 核心逻辑：锁定 sync_date 为数据源文件的日期
                        sync_date = file_date
                        sync_time = "00:00:00"
                        
                        # data_date 保留数据真实的发布日期
                        data_date = ""
                        if created_at and len(created_at) >= 10:
                            try:
                                data_date = created_at.split(' ')[0]
                                if ' ' in created_at:
                                    sync_time = created_at.split(' ')[1] 
                            except: pass
                        
                        if not data_date:
                            data_date = sync_date
                        
                        # 解析其他字段...
                        sentiment_info = item.get("sentiment_analysis", {})
                        sentiment = str(sentiment_info.get("sentiment", "Unknown"))
                        fine_grained_sentiment = str(sentiment_info.get("fine_grained_sentiment", "Unknown"))
                        intent = str(sentiment_info.get("intent", "Unknown"))
                        irony_detected = sentiment_info.get("irony_detected", False)
                        reasoning = str(sentiment_info.get("reasoning", ""))
                        
                        keywords = json.dumps(item.get("keywords", []), ensure_ascii=False)
                        ip_location = str(item.get("ip_location", ""))
                        top_id = str(item.get("top_id", ""))
                        visual_objects = json.dumps(item.get("visual_objects", []), ensure_ascii=False)
                        ocr_text = str(item.get("ocr_text", ""))
                        author = str(item.get("author", ""))
                        source = str(item.get("source", ""))
                        url = str(item.get("url", ""))
                        title = str(item.get("title", ""))
                        image_paths = json.dumps(item.get("image_paths", []), ensure_ascii=False)
                        video_path = str(item.get("video_path", ""))
                        
                        liked_count = item.get("liked_count") or item.get("comment_like_count") or 0
                        comments_count = item.get("comments_count") or item.get("sub_comment_count") or 0
                        shared_count = item.get("shared_count") or 0
                        collected_count = item.get("collected_count") or 0
                        gender = str(item.get("gender", ""))
                        content_text = str(item.get("content", ""))

                        parent_comment_id = str(item.get("parent_comment_id", ""))

                        batch_db.append((
                            unique_id, note_id, comment_id, top_id, data_date, sync_date, sync_time, created_at, 
                            content_text, sentiment, fine_grained_sentiment, intent, keywords, ip_location, visual_objects, 
                            ocr_text, author, source, liked_count, comments_count, shared_count, gender, parent_comment_id
                        ))

                        if comment_id == "0":
                            batch_content.append((
                                note_id, title, content_text, author, source, url, created_at, ip_location,
                                image_paths, video_path, liked_count, comments_count, shared_count, collected_count,
                                sentiment, fine_grained_sentiment, intent, irony_detected, reasoning,
                                keywords, visual_objects, ocr_text, sync_date, sync_time
                            ))
                        else:
                            batch_comments.append((
                                comment_id, note_id, content_text, author, source, url, created_at, ip_location,
                                gender, item.get("parent_comment_id", ""), liked_count, comments_count,
                                image_paths, sentiment, fine_grained_sentiment, intent, irony_detected, reasoning,
                                json.dumps(item.get("labels", []), ensure_ascii=False),
                                keywords, visual_objects, ocr_text, sync_date, sync_time
                            ))

                        if len(batch_db) >= 500:
                            cursor.executemany('INSERT OR REPLACE INTO processed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', batch_db)
                            if batch_content:
                                cursor.executemany('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', batch_content)
                            if batch_comments:
                                cursor.executemany('INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', batch_comments)
                            conn.commit()
                            total_synced += len(batch_db)
                            batch_db, batch_content, batch_comments = [], [], []
                            print(f"  Synced {total_synced} items...", end='\r')

                    except Exception as e:
                        continue
            
            # 提交剩余数据
            if batch_db:
                cursor.executemany('INSERT OR REPLACE INTO processed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', batch_db)
                if batch_content:
                    cursor.executemany('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', batch_content)
                if batch_comments:
                    cursor.executemany('INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', batch_comments)
                conn.commit()
                total_synced += len(batch_db)

    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    finally:
        cursor.execute("PRAGMA optimize")
        conn.close()
        print(f"\nRecovery complete. Total items updated/synced: {total_synced}")
        print("Now your dashboard trends should show data correctly distributed by their creation date.")

if __name__ == "__main__":
    sync_history()
