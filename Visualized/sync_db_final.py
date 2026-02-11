import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime

# Config
BASE_DIR = Path(__file__).parent.parent
LABELED_DATA_FILE = BASE_DIR / "Transformers" / "output" / "labeled_results.jsonl"
AGGREGATED_DATA_FILE = BASE_DIR / "Transformers" / "output" / "aggregated_display_data.json"
DB_PATH = BASE_DIR / "Transformers" / "cache" / "processed_ids.db"

def sync():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 彻底重新创建表，包含所有最新要求的字段
    cursor.execute("DROP TABLE IF EXISTS processed_items")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_items (
            unique_id TEXT PRIMARY KEY,
            note_id TEXT,
            comment_id TEXT,
            top_id TEXT,
            data_date TEXT,
            sync_date TEXT,
            created_at TEXT,
            content TEXT,
            sentiment TEXT,
            fine_grained_sentiment TEXT,
            intent TEXT,
            keywords TEXT,
            ip_location TEXT,
            visual_objects TEXT,
            ocr_text TEXT,
            author TEXT,
            source TEXT,
            liked_count INTEGER,
            comments_count INTEGER,
            shared_count INTEGER,
            gender TEXT
        )
    ''')

    # 同时也确保 content 和 comments 表存在
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS content (
            note_id TEXT PRIMARY KEY,
            title TEXT,
            content TEXT,
            author TEXT,
            source TEXT,
            url TEXT,
            created_at TEXT,
            ip_location TEXT,
            image_paths TEXT,
            video_path TEXT,
            liked_count INTEGER,
            comments_count INTEGER,
            shared_count INTEGER,
            collected_count INTEGER,
            sentiment TEXT,
            fine_grained_sentiment TEXT,
            intent TEXT,
            irony_detected BOOLEAN,
            reasoning TEXT,
            keywords TEXT,
            visual_objects TEXT,
            ocr_text TEXT,
            sync_date TEXT DEFAULT (date('now'))
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            comment_id TEXT PRIMARY KEY,
            note_id TEXT,
            content TEXT,
            author TEXT,
            source TEXT,
            url TEXT,
            created_at TEXT,
            ip_location TEXT,
            gender TEXT,
            parent_comment_id TEXT,
            comment_like_count INTEGER,
            sub_comment_count INTEGER,
            image_paths TEXT,
            sentiment TEXT,
            fine_grained_sentiment TEXT,
            intent TEXT,
            irony_detected BOOLEAN,
            reasoning TEXT,
            labels TEXT,
            keywords TEXT,
            visual_objects TEXT,
            ocr_text TEXT,
            sync_date TEXT DEFAULT (date('now')),
            FOREIGN KEY (note_id) REFERENCES content(note_id)
        )
    ''')
    
    db_entries = []
    content_entries = []
    comment_entries = []
    count = 0

    # 1. 处理 labeled_results.jsonl
    if LABELED_DATA_FILE.exists():
        print(f"Reading from {LABELED_DATA_FILE}...")
        with open(LABELED_DATA_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    note_id = str(item.get('note_id'))
                    comment_id = str(item.get('comment_id', '0'))
                    unique_id = f"{note_id}_{comment_id}"
                    
                    # 解析发布日期 (created_at)
                    created_at = item.get('created_at', '')
                    sync_date = datetime.now().strftime("%Y-%m-%d")
                    data_date = ""
                    if created_at:
                        try:
                            # 尝试解析多种日期格式
                            dt_str = created_at.split(' ')[0]
                            datetime.strptime(dt_str, "%Y-%m-%d")
                            data_date = dt_str
                        except:
                            data_date = item.get('data_date', '')
                    
                    if not data_date:
                        data_date = sync_date
                    
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
                    content = str(item.get("content", ""))
                    
                    db_entries.append((
                        unique_id, note_id, comment_id, top_id, data_date, sync_date, created_at, 
                        content, sentiment, fine_grained_sentiment, intent, keywords, ip_location, visual_objects, 
                        ocr_text, author, source, liked_count, comments_count, 
                        shared_count, gender
                    ))

                    # 同步到 content (articles) 或 comments 表
                    if comment_id == "0":
                        # 文章
                        content_entries.append((
                            note_id, title, content, author, source, url, created_at, ip_location,
                            image_paths, video_path, liked_count, comments_count, shared_count, collected_count,
                            sentiment, fine_grained_sentiment, intent, irony_detected, reasoning,
                            keywords, visual_objects, ocr_text, sync_date
                        ))
                    else:
                        # 评论
                        comment_entries.append((
                            comment_id, note_id, content, author, source, url, created_at, ip_location,
                            gender, item.get("parent_comment_id", ""), liked_count, comments_count,
                            image_paths, sentiment, fine_grained_sentiment, intent, irony_detected, reasoning,
                            json.dumps(item.get("labels", []), ensure_ascii=False),
                            keywords, visual_objects, ocr_text, sync_date
                        ))

                    count += 1
                    if len(db_entries) >= 1000:
                        cursor.executemany('INSERT OR REPLACE INTO processed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', db_entries)
                        if content_entries:
                            cursor.executemany('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', content_entries)
                        if comment_entries:
                            cursor.executemany('INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', comment_entries)
                        
                        db_entries = []
                        content_entries = []
                        comment_entries = []
                        print(f"Processed {count} entries...")
                except: continue

    # 2. 处理 aggregated_display_data.json
    if AGGREGATED_DATA_FILE.exists():
        print(f"Reading from {AGGREGATED_DATA_FILE}...")
        try:
            with open(AGGREGATED_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                sync_date = datetime.now().strftime("%Y-%m-%d")
                for post in data:
                    note_id = str(post.get('note_id'))
                    
                    # 处理评论
                    for comment in post.get('comments', []):
                        comment_id = str(comment.get('comment_id'))
                        unique_id = f"{note_id}_{comment_id}"
                        
                        created_at = comment.get('created_at', '')
                        data_date = created_at.split(' ')[0] if created_at else ""
                        
                        analysis = comment.get('analysis', {})
                        sentiment = str(analysis.get('sentiment', 'Unknown'))
                        fine_grained_sentiment = str(analysis.get('fine_grained_sentiment', 'Unknown'))
                        intent = str(analysis.get('intent', 'Unknown'))
                        content = str(comment.get('content', ''))
                        
                        db_entries.append((
                            unique_id, note_id, comment_id, str(post.get('top_id', '')),
                            data_date, sync_date, created_at, content,
                            sentiment, fine_grained_sentiment, intent, "[]", "", "[]", "",
                            str(comment.get('author', '')), str(post.get('source', '')),
                            0, 0, 0, ""
                        ))
                        count += 1
                        if len(db_entries) >= 1000:
                            cursor.executemany('INSERT OR REPLACE INTO processed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', db_entries)
                            db_entries = []
        except Exception as e:
            print(f"Error reading aggregated data: {e}")

    if db_entries:
        cursor.executemany('INSERT OR REPLACE INTO processed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', db_entries)
    if content_entries:
        cursor.executemany('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', content_entries)
    if comment_entries:
        cursor.executemany('INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', comment_entries)
    
    conn.commit()
    conn.close()
    print(f"Sync complete. Total entries: {count}")

if __name__ == "__main__":
    sync()
