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
    processed_items_sql = '''(
            unique_id TEXT PRIMARY KEY,
            note_id TEXT,
            comment_id TEXT,
            top_id TEXT,
            data_date TEXT,
            sync_date TEXT,
            sync_time TEXT,
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
            gender TEXT,
            parent_comment_id TEXT
        )'''
    
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
    ensure_columns("processed_items", processed_items_sql)
    ensure_columns("content", content_sql)
    ensure_columns("comments", comments_sql)
    
    # 创建索引以提高查询性能
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_sync_date ON content(sync_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_sentiment ON content(sentiment)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_sync_date ON comments(sync_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_sentiment ON comments(sentiment)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_note_id ON comments(note_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed_sync_date ON processed_items(sync_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed_unique_id ON processed_items(unique_id)")
    
    # 获取已存在的数据 ID 和 sync_date，用于增量更新判断
    cursor.execute("SELECT unique_id, sync_date FROM processed_items")
    existing_records = {row[0]: row[1] for row in cursor.fetchall()}
    print(f"Loaded {len(existing_records)} existing records from database.")

    db_entries = []
    content_entries = []
    comment_entries = []
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
                        if unique_id in existing_records:
                            last_sync_date = existing_records[unique_id]
                            # 如果文件日期比记录日期旧，跳过（保留较新的记录）
                            if file_sync_date < last_sync_date:
                                should_process = False
                            # 如果日期相同，且不是今天，跳过（假设历史数据稳定，不重复处理）
                            elif file_sync_date == last_sync_date and file_sync_date != today_str:
                                should_process = False
                            # 其他情况（文件日期更新，或日期相同且是今天），则处理（允许修正当天数据）

                        if not should_process:
                            skipped_count += 1
                            continue

                        # 记录本次运行状态
                        processed_in_current_run.add(unique_id)
                        existing_records[unique_id] = file_sync_date # 更新内存记录，防止同一批次内逻辑冲突
                        count += 1
                        if file_count % 100 == 0:
                            print(f"  Synced {count} new entries... (File: {file_path.name}, Line: {file_count}, Skipped: {skipped_count})", flush=True)
                        
                        # 保持 sync_date 与文件日期一致
                        sync_date = file_sync_date
                        sync_time = file_sync_time
                        
                        # 尝试从记录中恢复更具体的时间点
                        created_at = item.get("created_at", "")
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
                        
                        parent_comment_id = str(item.get("parent_comment_id", ""))
                        
                        db_entries.append((
                            unique_id, note_id, comment_id, top_id, data_date, sync_date, sync_time, created_at, 
                            content, sentiment, fine_grained_sentiment, intent, keywords, ip_location, visual_objects, 
                            ocr_text, author, source, liked_count, comments_count, 
                            shared_count, gender, parent_comment_id
                        ))

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
                            comment_entries.append((
                                comment_id, note_id, content, author, source, url, created_at, ip_location,
                                gender, parent_comment_id, liked_count, comments_count,
                                image_paths, sentiment, fine_grained_sentiment, intent, irony_detected, reasoning,
                                json.dumps(item.get("labels", []), ensure_ascii=False),
                                keywords, visual_objects, ocr_text, sync_date, sync_time
                            ))

                        if len(db_entries) >= 1000:
                            cursor.executemany('INSERT OR REPLACE INTO processed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', db_entries)
                            if content_entries:
                                cursor.executemany('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', content_entries)
                            if comment_entries:
                                cursor.executemany('INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', comment_entries)
                            conn.commit()
                            db_entries = []
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
                        
                        # 处理评论
                        for comment in post.get('comments', []):
                            comment_id = str(comment.get('comment_id'))
                            unique_id = f"{note_id}_{comment_id}"
                            
                            # 核心逻辑：智能增量更新
                            should_process = True
                            if unique_id in existing_records:
                                last_sync_date = existing_records[unique_id]
                                if file_sync_date < last_sync_date:
                                    should_process = False
                                elif file_sync_date == last_sync_date and file_sync_date != today_str:
                                    should_process = False
                            
                            if not should_process:
                                skipped_count += 1
                                continue
                                
                            processed_in_current_run.add(unique_id)
                            existing_records[unique_id] = file_sync_date
                            created_at = comment.get('created_at', '')
                            data_date = created_at.split(' ')[0] if created_at else ""
                            
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
                            content = str(comment.get('content', ''))
                            
                            db_entries.append((
                                unique_id, note_id, comment_id, str(post.get('top_id', '')),
                                data_date, file_sync_date, current_sync_time, created_at, content,
                                sentiment, fine_grained_sentiment, intent, "[]", "", "[]", "",
                                str(comment.get('author', '')), str(post.get('source', '')),
                                0, 0, 0, "", str(comment.get('parent_comment_id', ''))
                            ))
                            count += 1
                            if len(db_entries) >= 1000:
                                cursor.executemany('INSERT OR REPLACE INTO processed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', db_entries)
                                conn.commit()
                                db_entries = []
            except Exception as e:
                print(f"Error processing aggregated data file {file_path}: {e}")
    except KeyboardInterrupt:
        print("\nStopping sync process... saving progress...")
    finally:
        # 使用事务批量插入 content 和 comments，避免频繁索引更新
        if db_entries:
            cursor.executemany('INSERT OR REPLACE INTO processed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', db_entries)
        if content_entries:
            cursor.executemany('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', content_entries)
        if comment_entries:
            cursor.executemany('INSERT OR REPLACE INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', comment_entries)
        
        conn.commit()
        cursor.execute("PRAGMA optimize")
        conn.close()
        print(f"Sync complete. New entries: {count}, Skipped (already exists): {skipped_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Sync Transformers data to SQLite database.')
    parser.add_argument('--date', type=str, help='Specific date to sync (YYYY-MM-DD). If not provided, syncs all history data (skipping main empty file).')
    
    args = parser.parse_args()
    
    sync(target_date=args.date)
