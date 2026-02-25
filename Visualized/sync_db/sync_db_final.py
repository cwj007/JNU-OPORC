import json
import sqlite3
import os
import argparse
from pathlib import Path
from datetime import datetime

# Config
# Adjust BASE_DIR to point to JNU-OPORC root
current_path = Path(__file__).resolve().parent

def find_project_root(start_path):
    """向上查找直到找到包含 Transformers/output 的真正项目根目录"""
    path = start_path
    for _ in range(4): # 最多往上找4层
        # 检查关键数据文件或目录是否存在
        if (path / "Transformers" / "output").exists():
            return path
        path = path.parent
    return start_path.parent.parent # Fallback default

BASE_DIR = find_project_root(current_path)

LABELED_DATA_FILE = BASE_DIR / "Transformers" / "output" / "labeled_results.jsonl"
AGGREGATED_DATA_FILE = BASE_DIR / "Transformers" / "output" / "aggregated_display_data.json"
HISTORY_DIR = BASE_DIR / "Transformers" / "output" / "history"
DB_PATH = BASE_DIR / "Transformers" / "cache" / "processed_ids.db"
def sync(target_date=None):
    conn = sqlite3.connect(DB_PATH)
    # 启用高性能模式
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000") # 64MB 缓存
    conn.execute("PRAGMA temp_store=MEMORY")
    cursor = conn.cursor()
    
    # 确保表存在，包含所有最新要求的字段
    def ensure_columns(table_name, required_columns_sql):
        """安全地确保表存在并拥有所有列，不删除原有数据"""
        # 1. 创建表（如果不存在）
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} {required_columns_sql}")
        
        # 2. 检查缺失的列并添加
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {row[1] for row in cursor.fetchall()}
        
        # 解析 SQL 获取列名（简化版）
        import re
        cols_in_sql = re.findall(r'(\w+)\s+(?:TEXT|INTEGER|BOOLEAN|DATETIME)', required_columns_sql, re.IGNORECASE)
        
        for col in cols_in_sql:
            if col not in existing_cols:
                print(f"  Adding missing column {col} to table {table_name}...")
                # 尝试猜测类型，默认使用 TEXT
                col_type = "TEXT"
                if "count" in col.lower() or "id" in col.lower(): col_type = "INTEGER" if "id" not in col.lower() else "TEXT"
                if "detected" in col.lower(): col_type = "BOOLEAN"
                
                try:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type}")
                except Exception as e:
                    print(f"  Warning: Could not add column {col}: {e}")

    # 定义各个表的结构
    content_sql = '''(
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
            sync_date TEXT,
            sync_time TEXT,
            top_id TEXT
        )'''
    
    comments_sql = '''(
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
            sync_date TEXT,
            sync_time TEXT,
            FOREIGN KEY (note_id) REFERENCES content(note_id)
        )'''

    # 执行安全更新
    ensure_columns("content", content_sql)
    ensure_columns("comments", comments_sql)
    
    # 创建索引以提高查询性能
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_sync_date ON content(sync_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_sentiment ON content(sentiment)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_sync_date ON comments(sync_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_sentiment ON comments(sentiment)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_note_id ON comments(note_id)")
    
    # 获取已存在的数据 ID 和 sync_date，用于增量更新判断
    # 从 content 表获取 (note_id, sync_date)
    cursor.execute("SELECT note_id, sync_date FROM content")
    existing_content = {row[0]: row[1] for row in cursor.fetchall()}
    
    # 从 comments 表获取 (comment_id, sync_date)
    cursor.execute("SELECT comment_id, sync_date FROM comments")
    existing_comments = {row[0]: row[1] for row in cursor.fetchall()}
    
    print(f"Loaded {len(existing_content)} content records and {len(existing_comments)} comment records from database.")
    content_entries = []
    comment_entries = []
    referenced_parents = {} # Track note_id -> source for placeholder creation

    # 获取待处理文件列表
    labeled_files = []
    aggregated_files = []

    # 记录本次运行已处理的ID，防止同一次运行中重复处理
    processed_in_current_run = set()
    today_str = datetime.now().strftime("%Y-%m-%d")

    if target_date:
        print(f"Running in Date Specific Mode: {target_date}")
        if HISTORY_DIR.exists():
            # 查找匹配日期的历史文件
            date_labeled = list(HISTORY_DIR.glob(f"labeled_results_{target_date}.jsonl"))
            if date_labeled:
                print(f"Found {len(date_labeled)} labeled files for date {target_date}")
                labeled_files.extend(date_labeled)
            
            date_agg = list(HISTORY_DIR.glob(f"aggregated_{target_date}.json"))
            if date_agg:
                print(f"Found {len(date_agg)} aggregated files for date {target_date}")
                aggregated_files.extend(date_agg)
            
            if not labeled_files and not aggregated_files:
                print(f"No history files found for date: {target_date}")
                conn.close()
                return
    else:
        print("Running in History Only Mode (Scanning all history files)")
        # Skip main LABELED_DATA_FILE as requested
        # if LABELED_DATA_FILE.exists():
        #     labeled_files.append(LABELED_DATA_FILE)
        
        if HISTORY_DIR.exists():
            history_labeled = list(HISTORY_DIR.glob("labeled_results_*.jsonl"))
            print(f"Found {len(history_labeled)} history labeled files in {HISTORY_DIR}")
            labeled_files.extend(history_labeled)

        # Skip main AGGREGATED_DATA_FILE as requested
        # if AGGREGATED_DATA_FILE.exists():
        #     aggregated_files.append(AGGREGATED_DATA_FILE)
        
        if HISTORY_DIR.exists():
            history_agg = list(HISTORY_DIR.glob("aggregated_*.json"))
            print(f"Found {len(history_agg)} history aggregated files in {HISTORY_DIR}")
            aggregated_files.extend(history_agg)

    count = 0
    skipped_count = 0
    try:
        # 1. 处理 labeled_results 文件
        for file_path in labeled_files:
            print(f"Processing labeled file: {file_path}", flush=True)
            # 核心逻辑：从文件名提取日期作为 sync_date 的基准
            file_sync_date = ""
            if "_" in file_path.name:
                try:
                    # 尝试匹配格式如 labeled_results_2026-02-12.jsonl 中的日期
                    parts = file_path.name.split("_")
                    for part in parts:
                        date_part = part.split(".")[0]
                        if len(date_part) == 10 and date_part.count("-") == 2:
                            datetime.strptime(date_part, "%Y-%m-%d")
                            file_sync_date = date_part
                            break
                except: pass
            
            # 如果文件名没日期，则使用文件修改日期
            if not file_sync_date:
                mtime = os.path.getmtime(file_path)
                file_sync_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            
            file_sync_time = "00:00:00" # 历史文件默认为 0 点，主文件稍后会尝试从记录中恢复
            print(f"  Target sync date set to: {file_sync_date} (from filename/mtime)")

            file_count = 0
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    file_count += 1
                    
                    try:
                        item = json.loads(line)
                        # 只有当项是字典且包含必要 ID 时才处理
                        if not isinstance(item, dict):
                            continue
                        
                        note_id = str(item.get('note_id', ''))
                        comment_id = str(item.get('comment_id', '0'))
                        if not note_id:
                            continue
                            
                        unique_id = f"{note_id}_{comment_id}"
                        
                        # 核心逻辑：智能增量更新
                        should_process = True
                        
                        if comment_id == "0":
                            # 文章检查
                            if note_id in existing_content:
                                last_sync_date = existing_content[note_id]
                                if file_sync_date < last_sync_date:
                                    should_process = False
                                elif file_sync_date == last_sync_date and file_sync_date != today_str:
                                    should_process = False
                        else:
                            # 评论检查
                            if comment_id in existing_comments:
                                last_sync_date = existing_comments[comment_id]
                                if file_sync_date < last_sync_date:
                                    should_process = False
                                elif file_sync_date == last_sync_date and file_sync_date != today_str:
                                    should_process = False

                        if not should_process:
                            skipped_count += 1
                            continue

                        # 记录本次运行状态
                        processed_in_current_run.add(unique_id)
                        if comment_id == "0":
                            existing_content[note_id] = file_sync_date
                        else:
                            existing_comments[comment_id] = file_sync_date
                        
                        count += 1
                        if file_count % 100 == 0:
                            print(f"  Synced {count} new entries... (File: {file_path.name}, Line: {file_count}, Skipped: {skipped_count})", flush=True)
                        
                        # 保持 sync_date 与文件日期一致
                        sync_date = file_sync_date
                        sync_time = file_sync_time
                        
                        # 尝试从记录中恢复更具体的时间点
                        created_at = str(item.get("created_at", ""))
                        
                        # Fix: Ensure created_at is in YYYY-MM-DD HH:MM:SS format if it's a timestamp
                        try:
                            if created_at.isdigit():
                                ts_int = int(created_at)
                                if ts_int > 1000000000000: ts_int = ts_int / 1000
                                dt = datetime.fromtimestamp(ts_int)
                                created_at = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            pass

                        if created_at and ' ' in created_at:
                            try:
                                sync_time = created_at.split(' ')[1]
                            except: pass

                        data_date = ""
                        if created_at:
                            try:
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
                        author = str(item.get("author", ""))
                        source = str(item.get("source", ""))
                        url = str(item.get("url", ""))
                        title = str(item.get("title", ""))
                        top_id = str(item.get("top_id", ""))
                        # Fix: Ensure Zhihu items have a valid top_id (use note_id)
                        if source == '知乎' and (not top_id or top_id == 'None' or top_id == 'null'):
                            top_id = str(item.get('note_id', ''))
                        visual_objects = json.dumps(item.get("visual_objects", []), ensure_ascii=False)
                        ocr_text = str(item.get("ocr_text", ""))
                        image_paths = json.dumps(item.get("image_paths", []), ensure_ascii=False)
                        video_path = str(item.get("video_path", ""))
                        
                        liked_count = item.get("liked_count") or item.get("comment_like_count") or 0
                        comments_count = item.get("comments_count") or item.get("sub_comment_count") or 0
                        shared_count = item.get("shared_count") or 0
                        collected_count = item.get("collected_count") or 0
                        gender = str(item.get("gender", ""))
                        content = str(item.get("content", ""))
                        
                        parent_comment_id = str(item.get("parent_comment_id", ""))
                        
                        # 同步到 content (articles) 或 comments 表
                        if comment_id == "0":
                            # 文章
                            content_entries.append((
                                note_id, title, content, author, source, url, created_at, ip_location,
                                image_paths, video_path, liked_count, comments_count, shared_count, collected_count,
                                sentiment, fine_grained_sentiment, intent, irony_detected, reasoning,
                                keywords, visual_objects, ocr_text, sync_date, sync_time, top_id
                            ))
                        else:
                            # 评论
                            # Track parent note_id and source for potential placeholder creation
                            if note_id and source:
                                referenced_parents[note_id] = source
                                
                            comment_entries.append((
                                comment_id, note_id, content, author, source, url, created_at, ip_location,
                                gender, parent_comment_id, liked_count, comments_count,
                                image_paths, sentiment, fine_grained_sentiment, intent, irony_detected, reasoning,
                                json.dumps(item.get("labels", []), ensure_ascii=False),
                                keywords, visual_objects, ocr_text, sync_date, sync_time
                            ))

                        if len(content_entries) + len(comment_entries) >= 1000:
                            if content_entries:
                                cursor.executemany('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', content_entries)
                            
                            # Insert placeholders for missing parents before inserting comments
                            if referenced_parents:
                                placeholder_entries = []
                                for nid, src in referenced_parents.items():
                                    placeholder_entries.append((
                                        nid, "Unknown Title (Zhihu/Weibo)", "Parent article content missing", "Unknown Author", src, "", sync_date, "",
                                        "[]", "", 0, 0, 0, 0,
                                        "Neutral", "None", "None", False, "",
                                        "[]", "[]", "", sync_date, sync_time, ""
                                    ))
                                try:
                                    cursor.executemany('INSERT OR IGNORE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', placeholder_entries)
                                except Exception as e:
                                    print(f"  Warning: Failed to insert placeholders: {e}")
                                referenced_parents = {}

                            if comment_entries:
                                cursor.executemany('INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', comment_entries)
                            conn.commit()
                            content_entries = []
                            comment_entries = []
                    except Exception as e:
                        print(f"  Error processing line {file_count}: {e}")
                        continue

        # 2. 处理 aggregated_display_data.json
        for file_path in aggregated_files:
            print(f"Processing aggregated file: {file_path}", flush=True)
            try:
                # 尝试从文件名提取日期
                file_sync_date = ""
                if "_" in file_path.name:
                    try:
                        parts = file_path.name.split("_")
                        for part in parts:
                            date_part = part.split(".")[0]
                            if len(date_part) == 10 and date_part.count("-") == 2:
                                datetime.strptime(date_part, "%Y-%m-%d")
                                file_sync_date = date_part
                                break
                    except: pass
                
                if not file_sync_date:
                    file_sync_date = datetime.now().strftime("%Y-%m-%d")
                    print(f"  Target sync date set to: {file_sync_date} (Today/Default)")
                else:
                    print(f"  Target sync date set to: {file_sync_date} (from filename)")

                file_sync_time = datetime.now().strftime("%H:%M:%S")

                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    sync_date = file_sync_date
                    sync_time = file_sync_time
                    for post in data:
                        note_id = str(post.get('note_id'))
                        source = str(post.get('source', ''))
                        top_id = str(post.get('top_id', ''))
                        
                        # 处理文章本身 (aggregated 文件可能包含文章更新)
                        if note_id in existing_content:
                            last_sync_date = existing_content[note_id]
                            if file_sync_date < last_sync_date:
                                pass # Skip update but process comments
                            elif file_sync_date == last_sync_date and file_sync_date != today_str:
                                pass
                            else:
                                content_entries.append((
                                    note_id, str(post.get('title', '')), str(post.get('content', '')),
                                    str(post.get('author', '')), source, str(post.get('url', '')),
                                    str(post.get('created_at', '')), str(post.get('ip_location', '')),
                                    json.dumps(post.get('image_paths', []), ensure_ascii=False),
                                    str(post.get('video_path', '')), post.get('liked_count', 0),
                                    post.get('comments_count', 0), post.get('shared_count', 0),
                                    post.get('collected_count', 0), "Neutral", "None", "None",
                                    False, "", "[]", "[]", "", file_sync_date, file_sync_time, top_id
                                ))

                        # 处理评论
                        for comment in post.get('comments', []):
                            comment_id = str(comment.get('comment_id'))
                            unique_id = f"{note_id}_{comment_id}"
                            
                            # 核心逻辑：智能增量更新
                            should_process = True
                            if comment_id in existing_comments:
                                last_sync_date = existing_comments[comment_id]
                                if file_sync_date < last_sync_date:
                                    should_process = False
                                elif file_sync_date == last_sync_date and file_sync_date != today_str:
                                    should_process = False
                            
                            if not should_process:
                                skipped_count += 1
                                continue
                                
                            processed_in_current_run.add(unique_id)
                            existing_comments[comment_id] = file_sync_date
                            created_at = comment.get('created_at', '')
                            
                            # 历史文件尝试恢复时间，但日期强制设为今天
                            current_sync_time = file_sync_time
                            if created_at and ' ' in created_at:
                                try:
                                    current_sync_time = created_at.split(' ')[1]
                                except: pass

                            analysis = comment.get('analysis', {})
                            sentiment = str(analysis.get('sentiment', 'Unknown'))
                            fine_grained_sentiment = str(analysis.get('fine_grained_sentiment', 'Unknown'))
                            intent = str(analysis.get('intent', 'Unknown'))
                            content_text = str(comment.get('content', ''))
                            
                            # Track parent note_id and source
                            if note_id and source:
                                referenced_parents[note_id] = source

                            comment_entries.append((
                                comment_id, note_id, content_text, str(comment.get('author', '')),
                                source, str(comment.get('url', '')), created_at,
                                str(comment.get('ip_location', '')), str(comment.get('gender', '')),
                                str(comment.get('parent_comment_id', '')), comment.get('liked_count', 0),
                                comment.get('sub_comment_count', 0), "[]", sentiment,
                                fine_grained_sentiment, intent, False, "", "[]", "[]", "[]", "",
                                file_sync_date, current_sync_time
                            ))
                            count += 1
                            
                            if len(content_entries) + len(comment_entries) >= 1000:
                                if content_entries:
                                    cursor.executemany('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', content_entries)
                                
                                if referenced_parents:
                                    placeholder_entries = []
                                    for nid, src in referenced_parents.items():
                                        placeholder_entries.append((
                                            nid, "Unknown Title", "Content missing", "Unknown", src, "", file_sync_date, "",
                                            "[]", "", 0, 0, 0, 0, "Neutral", "None", "None", False, "", "[]", "[]", "", file_sync_date, file_sync_time, ""
                                        ))
                                    cursor.executemany('INSERT OR IGNORE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', placeholder_entries)
                                    referenced_parents = {}

                                if comment_entries:
                                    cursor.executemany('INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', comment_entries)
                                conn.commit()
                                content_entries = []
                                comment_entries = []
            except Exception as e:
                print(f"Error processing aggregated data file {file_path}: {e}")
    except KeyboardInterrupt:
        print("\nStopping sync process... saving progress...")
    finally:
        # 3. 处理完成后，进行最后的提交
        if content_entries:
            cursor.executemany('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', content_entries)
        
        # Insert placeholders for missing parents before inserting comments
        if referenced_parents:
            placeholder_entries = []
            for nid, src in referenced_parents.items():
                placeholder_entries.append((
                    nid, "Unknown Title (Zhihu/Weibo)", "Parent article content missing", "Unknown Author", src, "", today_str, "",
                    "[]", "", 0, 0, 0, 0,
                    "Neutral", "None", "None", False, "",
                    "[]", "[]", "", today_str, "00:00:00", ""
                ))
            try:
                cursor.executemany('INSERT OR IGNORE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', placeholder_entries)
            except Exception as e:
                print(f"  Warning: Failed to insert placeholders: {e}")

        if comment_entries:
            cursor.executemany('INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', comment_entries)
        
        conn.commit()
        
        # 删除旧表 processed_items
        cursor.execute("DROP TABLE IF EXISTS processed_items")
        conn.commit()
        
        conn.close()
        print(f"Sync complete. Total synced: {count}, Total skipped: {skipped_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Sync Transformers data to SQLite database.')
    parser.add_argument('--date', type=str, help='Specific date to sync (YYYY-MM-DD). If not provided, syncs all history data (skipping main empty file).')
    
    args = parser.parse_args()
    
    sync(target_date=args.date)
