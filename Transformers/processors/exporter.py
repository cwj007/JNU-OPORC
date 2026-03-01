import json
import os
import csv
import sqlite3
import threading
import queue
import time
from urllib.parse import unquote
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from filelock import FileLock

from ..config import PLATFORM_MAP, HISTORICAL_LABELED_DIR, TRANSFORMERS_DIR, CACHE_DIR
from Transformers import utils

class Exporter:
    def __init__(self, output_file: str, formats: List[str] = None):
        self.output_file = Path(output_file)
        self.formats = formats or ["json"]
        self.db_path = CACHE_DIR / "processed_ids.db"
        self._ensure_table_exists()
        
        # 异步写入队列
        self.write_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.write_thread = threading.Thread(target=self._async_write_worker, daemon=True)
        self.write_thread.start()

    def _ensure_table_exists(self):
        """确保数据库表存在，如果不存在则创建，如果存在则检查字段并升级。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 1. 创建 content 表
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
                sync_date TEXT,
                sync_time TEXT,
                top_id TEXT
            )
        ''')

        # 2. 创建 comments 表
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
                sync_date TEXT,
                sync_time TEXT,
                FOREIGN KEY (note_id) REFERENCES content(note_id)
            )
        ''')

        # 3. 创建 top_topics 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS top_topics (
                top_id TEXT PRIMARY KEY,
                top_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 字段升级逻辑 (确保所有字段都存在)
        def upgrade_table(table_name, required_fields):
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_cols = {c[1] for c in cursor.fetchall()}
            for field_name, field_type in required_fields:
                if field_name not in existing_cols:
                    try:
                        cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {field_name} {field_type}')
                    except sqlite3.OperationalError as e:
                        utils.logger.warning(f"Could not add column {field_name} to {table_name}: {e}")

        content_fields = [
            ('note_id', 'TEXT'), ('title', 'TEXT'), ('content', 'TEXT'), ('author', 'TEXT'),
            ('source', 'TEXT'), ('url', 'TEXT'), ('created_at', 'TEXT'), ('ip_location', 'TEXT'),
            ('image_paths', 'TEXT'), ('video_path', 'TEXT'), ('liked_count', 'INTEGER'),
            ('comments_count', 'INTEGER'), ('shared_count', 'INTEGER'), ('collected_count', 'INTEGER'),
            ('sentiment', 'TEXT'), ('fine_grained_sentiment', 'TEXT'), ('intent', 'TEXT'),
            ('irony_detected', 'BOOLEAN'), ('reasoning', 'TEXT'), ('keywords', 'TEXT'),
            ('visual_objects', 'TEXT'), ('ocr_text', 'TEXT'), ('sync_date', 'TEXT'),
            ('sync_time', 'TEXT'), ('top_id', 'TEXT')
        ]
        upgrade_table('content', content_fields)

        comment_fields = [
            ('comment_id', 'TEXT'), ('note_id', 'TEXT'), ('content', 'TEXT'), ('author', 'TEXT'),
            ('source', 'TEXT'), ('url', 'TEXT'), ('created_at', 'TEXT'), ('ip_location', 'TEXT'),
            ('gender', 'TEXT'), ('parent_comment_id', 'TEXT'), ('comment_like_count', 'INTEGER'),
            ('sub_comment_count', 'INTEGER'), ('image_paths', 'TEXT'), ('sentiment', 'TEXT'),
            ('fine_grained_sentiment', 'TEXT'), ('intent', 'TEXT'), ('irony_detected', 'BOOLEAN'),
            ('reasoning', 'TEXT'), ('labels', 'TEXT'), ('keywords', 'TEXT'),
            ('visual_objects', 'TEXT'), ('ocr_text', 'TEXT'), ('sync_date', 'TEXT'),
            ('sync_time', 'TEXT')
        ]
        upgrade_table('comments', comment_fields)

        # 检查是否需要删除旧表 processed_items
        # 根据用户要求，删除旧表
        cursor.execute("DROP TABLE IF EXISTS processed_items")
        
        conn.commit()
        conn.close()

    def get_existing_ids(self) -> set:
        """从 SQLite 数据库中获取所有已处理的 ID，格式为 note_id_comment_id。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 文章 ID 格式为 note_id_0
        cursor.execute('SELECT note_id FROM content')
        note_ids = {f"{row[0]}_0" for row in cursor.fetchall()}
        
        # 评论 ID 格式为 note_id_comment_id
        cursor.execute('SELECT note_id, comment_id FROM comments')
        comment_ids = {f"{row[0]}_{row[1]}" for row in cursor.fetchall()}
        
        conn.close()
        return note_ids.union(comment_ids)

    def _is_id_processed(self, note_id: str, comment_id: str = '0') -> bool:
        """在数据库中检查单条 ID 是否存在。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if comment_id == '0' or not comment_id:
            cursor.execute('SELECT 1 FROM content WHERE note_id = ?', (note_id,))
        else:
            cursor.execute('SELECT 1 FROM comments WHERE comment_id = ?', (comment_id,))
            
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def get_post_analysis(self, note_id: str) -> Optional[Dict[str, Any]]:
        """从数据库获取已处理的文章分析结果（用于为评论提供上下文）。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT sentiment, intent, visual_objects, ocr_text, content 
                FROM content 
                WHERE note_id = ?
                LIMIT 1
            ''', (note_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "sentiment": row[0],
                    "intent": row[1],
                    "visual_objects": json.loads(row[2]) if row[2] else [],
                    "ocr_text": row[3],
                    "content": row[4]
                }
            return None
        except Exception as e:
            utils.logger.error(f"[Exporter.get_post_analysis] 查询失败: {e}")
            return None
        finally:
            conn.close()

    def _mark_ids_as_processed(self, content_entries: List[tuple], comment_entries: List[tuple]):
        """批量将内容和评论存入数据库。"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cursor = conn.cursor()
        
        if content_entries:
            cursor.executemany('''
                INSERT OR REPLACE INTO content (
                    note_id, title, content, author, source, url, created_at, ip_location,
                    image_paths, video_path, liked_count, comments_count, shared_count,
                    collected_count, sentiment, fine_grained_sentiment, intent,
                    irony_detected, reasoning, keywords, visual_objects, ocr_text,
                    sync_date, sync_time, top_id
                ) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', content_entries)
            
        if comment_entries:
            cursor.executemany('''
                INSERT OR REPLACE INTO comments (
                    comment_id, note_id, content, author, source, url, created_at, ip_location,
                    gender, parent_comment_id, comment_like_count, sub_comment_count,
                    image_paths, sentiment, fine_grained_sentiment, intent,
                    irony_detected, reasoning, labels, keywords, visual_objects, ocr_text,
                    sync_date, sync_time
                ) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', comment_entries)
            
        conn.commit()
        conn.close()

    def export(self, analyzed_data: List[Dict[str, Any]], append: bool = False, use_lock: bool = True):
        """将数据丢入异步队列，立即返回，不阻塞 GPU。"""
        if not analyzed_data:
            return
        
        # 将任务包装后放入队列
        self.write_queue.put({
            "data": analyzed_data,
            "append": append,
            "use_lock": use_lock
        })

    def _async_write_worker(self):
        """后台写入线程：负责处理 IO 密集型任务。"""
        while not (self.stop_event.is_set() and self.write_queue.empty()):
            try:
                # 阻塞式获取任务，超时时间 1 秒以便检查停止事件
                task = self.write_queue.get(timeout=1.0)
                
                analyzed_data = task["data"]
                append = task["append"]
                use_lock = task["use_lock"]
                
                self._process_export_task(analyzed_data, append, use_lock)
                
                self.write_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                # 打印完整的错误堆栈，方便调试
                import traceback
                traceback.print_exc()
                utils.logger.error(f"  [Exporter._async_write_worker] 后台线程异常: {e}")

    def _process_export_task(self, analyzed_data: List[Dict[str, Any]], append: bool, use_lock: bool):
        """实际的写入逻辑：格式化、去重、存库、写文件。"""
        # 1. 过滤已存在的 ID (使用 SQLite 极速查询)
        valid_entries = []
        content_entries = []
        comment_entries = []
        top_entries = {} # top_id -> top_name
        sync_date = datetime.now().strftime("%Y-%m-%d")
        sync_time = datetime.now().strftime("%H:%M:%S")
        data_date = analyzed_data[0].get("data_date")
        
        # 批量获取当前批次的所有 ID 状态，减少数据库连接开销
        conn = sqlite3.connect(self.db_path)
        # 启用读性能优化
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.cursor()
        
        for item in analyzed_data:
            # 兼容处理：如果 item 已经是格式化好的 entry，直接使用
            if "sentiment_analysis" in item:
                entry = item
            else:
                entry = self._format_entry(item)
                
            note_id = str(entry.get('note_id'))
            comment_id = str(entry.get('comment_id', '0'))
            
            # 检查 ID 是否已处理 (根据类型检查不同表)
            if comment_id == '0' or not comment_id:
                cursor.execute('SELECT 1 FROM content WHERE note_id = ?', (note_id,))
            else:
                cursor.execute('SELECT 1 FROM comments WHERE comment_id = ?', (comment_id,))
                
            if cursor.fetchone() is not None:
                continue
                
            valid_entries.append(entry)
            
            # 提取通用字段
            sentiment_data = entry.get("sentiment_analysis", {})
            sentiment = str(sentiment_data.get("sentiment", "Unknown"))
            fine_grained_sentiment = str(sentiment_data.get("fine_grained_sentiment", "Unknown"))
            intent = str(sentiment_data.get("intent", "Unknown"))
            irony_detected = sentiment_data.get("irony_detected", False)
            reasoning = str(sentiment_data.get("reasoning", ""))
            
            keywords = json.dumps(entry.get("keywords", []), ensure_ascii=False)
            ip_location = str(entry.get("ip_location", ""))
            author = str(entry.get("author", ""))
            source = str(entry.get("source", ""))
            url = str(entry.get("url", ""))
            top_id = str(entry.get("top_id", ""))
            top_name = entry.get("top_name")
            
            # Fix: Ensure Zhihu items have a valid top_id (use note_id)
            if source == '知乎' and (not top_id or top_id == 'None' or top_id == 'null'):
                top_id = str(entry.get('note_id', ''))
                
            created_at = str(entry.get("created_at", ""))
            content_text = str(entry.get("content", ""))
            visual_objects = json.dumps(entry.get("visual_objects", []), ensure_ascii=False)
            ocr_text = str(entry.get("ocr_text", ""))
            image_paths = json.dumps(entry.get("image_paths", []), ensure_ascii=False)
            
            if comment_id == '0' or not comment_id:
                # content 表字段
                title = str(entry.get("title", ""))
                video_path = str(entry.get("video_path", ""))
                liked_count = entry.get("liked_count") or 0
                comments_count = entry.get("comments_count") or 0
                shared_count = entry.get("shared_count") or 0
                collected_count = entry.get("collected_count") or 0
                
                content_entries.append((
                    note_id, title, content_text, author, source, url, created_at, ip_location,
                    image_paths, video_path, liked_count, comments_count, shared_count,
                    collected_count, sentiment, fine_grained_sentiment, intent,
                    irony_detected, reasoning, keywords, visual_objects, ocr_text,
                    sync_date, sync_time, top_id
                ))
            else:
                # comments 表字段
                gender = str(entry.get("gender", ""))
                parent_comment_id = str(entry.get("parent_comment_id", ""))
                comment_like_count = entry.get("comment_like_count") or entry.get("liked_count") or 0
                sub_comment_count = entry.get("sub_comment_count") or entry.get("comments_count") or 0
                labels = json.dumps(entry.get("labels", []), ensure_ascii=False)
                
                comment_entries.append((
                    comment_id, note_id, content_text, author, source, url, created_at, ip_location,
                    gender, parent_comment_id, comment_like_count, sub_comment_count,
                    image_paths, sentiment, fine_grained_sentiment, intent,
                    irony_detected, reasoning, labels, keywords, visual_objects, ocr_text,
                    sync_date, sync_time
                ))

            # 记录 top_topics
            if top_id and top_id != "None":
                if top_name:
                    top_entries[top_id] = top_name
                else:
                    # 如果没有 top_name，尝试从 top_id 解码
                    top_entries[top_id] = unquote(top_id)

        conn.close()

        if not valid_entries:
            return

        # 2. 写入文件 (根据配置格式)
        self._write_to_jsonl(valid_entries, data_date, append, use_lock)
            
        if "csv" in self.formats:
            self._write_to_csv(valid_entries, data_date, append, use_lock)

        if "sqlite" in self.formats:
            self._write_to_sqlite_export(valid_entries, data_date)

        # 3. 写入数据库索引
        self._mark_ids_as_processed(content_entries, comment_entries)
        
        # 4. 写入 top_topics 表
        if top_entries:
            self._update_top_topics(top_entries)
        
        # 5. 输出存储日志
        utils.logger.info(f"[Exporter._process_export_task] 存储: {len(valid_entries)} 条新记录已异步同步 (Formats: {self.formats})")

    def _update_top_topics(self, top_entries: Dict[str, str]):
        """批量更新 top_topics 表。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # 确保表存在
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS top_topics (
                top_id TEXT PRIMARY KEY,
                top_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        entries = [(tid, tname) for tid, tname in top_entries.items()]
        cursor.executemany('''
            INSERT OR REPLACE INTO top_topics (top_id, top_name) VALUES (?, ?)
        ''', entries)
        conn.commit()
        conn.close()

    def _write_to_jsonl(self, valid_entries, data_date, append, use_lock):
        """写入 JSONL 文件。"""
        # 1. 写入临时文件
        # 注意：这里我们使用 output_file 作为 JSONL 的路径 (如果它以 .jsonl 结尾)
        # 如果 output_file 没有扩展名，我们应该加上 .jsonl
        # 但为了保持兼容性，我们假设 output_file 就是 jsonl 路径
        jsonl_file = self.output_file
        if jsonl_file.suffix != '.jsonl':
             jsonl_file = jsonl_file.with_suffix('.jsonl')

        temp_main = f"{jsonl_file}.tmp"
        mode = 'a' if append else 'w'
        
        try:
            with open(temp_main, 'w', encoding='utf-8') as f:
                for entry in valid_entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            # 2. 无论是否有 data_date，都写入主文件 (labeled_results.jsonl)
            def write_main():
                with open(jsonl_file, 'a', encoding='utf-8') as f:
                    with open(temp_main, 'r', encoding='utf-8') as tf:
                        f.write(tf.read())
                        
            if use_lock:
                 with FileLock(f"{jsonl_file}.lock"):
                     write_main()
            else:
                 write_main()

            # 3. 写入历史文件 (如果有 data_date 则使用 data_date，否则使用当前日期)
            target_date = data_date if data_date else datetime.now().strftime("%Y-%m-%d")
            
            # Debug log to confirm writing
            utils.logger.info(f"[Exporter] Writing backup to history file: labeled_results_{target_date}.jsonl")
            
            history_file = HISTORICAL_LABELED_DIR / f"labeled_results_{target_date}.jsonl"
            with open(history_file, 'a', encoding='utf-8') as f:
                with open(temp_main, 'r', encoding='utf-8') as tf:
                    f.write(tf.read())
            
            # 更新聚合 JSON
            self._export_aggregated_data(valid_entries, target_date, True)
            
        finally:
            if os.path.exists(temp_main):
                os.remove(temp_main)

    def _write_to_csv(self, valid_entries, data_date, append, use_lock):
        """写入 CSV 文件。"""
        csv_file = self.output_file.with_suffix(".csv")
        
        # Flatten entries
        flat_entries = []
        headers = set()
        
        for entry in valid_entries:
            flat = entry.copy()
            # Flatten sentiment_analysis
            sa = flat.pop('sentiment_analysis', {})
            flat.update(sa)
            
            # Convert lists/dicts to string
            for k, v in flat.items():
                if isinstance(v, (list, dict)):
                    flat[k] = json.dumps(v, ensure_ascii=False)
                elif v is None:
                    flat[k] = ""
            
            flat_entries.append(flat)
            headers.update(flat.keys())
            
        # Define standard header order
        ordered_headers = ['note_id', 'comment_id', 'content', 'sentiment', 'intent', 'fine_grained_sentiment', 'irony_detected', 'reasoning']
        # Add remaining headers
        ordered_headers.extend(sorted([h for h in headers if h not in ordered_headers]))
        
        mode = 'a' if append and csv_file.exists() else 'w'
        write_header = not (append and csv_file.exists())
        
        def write_action():
            # utf-8-sig for Excel compatibility
            with open(csv_file, mode, newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=ordered_headers)
                if write_header:
                    writer.writeheader()
                writer.writerows(flat_entries)
                
        if use_lock:
            with FileLock(f"{csv_file}.lock"):
                write_action()
        else:
            write_action()

    def _write_to_sqlite_export(self, valid_entries, data_date):
        """导出到用户可见的 SQLite 数据库。"""
        db_file = self.output_file.with_suffix(".db")
        conn = sqlite3.connect(db_file)
        
        flat_entries = []
        all_keys = set()
        for entry in valid_entries:
            flat = entry.copy()
            sa = flat.pop('sentiment_analysis', {})
            flat.update(sa)
            
            processed = {}
            for k, v in flat.items():
                if isinstance(v, (list, dict)):
                    processed[k] = json.dumps(v, ensure_ascii=False)
                else:
                    processed[k] = v
            flat_entries.append(processed)
            all_keys.update(processed.keys())
            
        # Create table
        cols_def = []
        for k in sorted(all_keys):
            cols_def.append(f'"{k}" TEXT') 
            
        cols_sql = ", ".join(cols_def)
        # 使用 labeled_data 作为表名
        create_sql = f"CREATE TABLE IF NOT EXISTS labeled_data ({cols_sql})"
        
        try:
            cursor = conn.cursor()
            cursor.execute(create_sql)
            
            # Add missing columns if any
            cursor.execute("PRAGMA table_info(labeled_data)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            for k in all_keys:
                if k not in existing_cols:
                    cursor.execute(f'ALTER TABLE labeled_data ADD COLUMN "{k}" TEXT')
            
            # Insert data
            for item in flat_entries:
                keys = list(item.keys())
                placeholders = ",".join(["?"] * len(keys))
                cols = ",".join([f'"{k}"' for k in keys])
                values = [item[k] for k in keys]
                cursor.execute(f"INSERT INTO labeled_data ({cols}) VALUES ({placeholders})", values)
                
            conn.commit()
        except Exception as e:
            utils.logger.error(f"Error exporting to SQLite: {e}")
        finally:
            conn.close()

    def close(self):
        """关闭 Exporter，确保所有数据写完。"""
        self.stop_event.set()
        if self.write_thread.is_alive():
            self.write_thread.join()

    def _export_aggregated_data(self, results: List[Dict[str, Any]], data_date: str, append: bool):
        """将数据按文章聚合，并对标签/关键词进行去重，生成前端易用的 JSON。"""
        # 如果提供了 data_date，则优先使用历史文件
        if data_date:
            agg_file = HISTORICAL_LABELED_DIR / f"aggregated_{data_date}.json"
        else:
            agg_file = self.output_file.parent / "aggregated_display_data.json"
        
        # 如果是追加模式，先读取现有数据
        aggregated = {}
        if append and agg_file.exists():
            try:
                with open(agg_file, 'r', encoding='utf-8') as f:
                    old_list = json.load(f)
                    for entry in old_list:
                        # 转换回 set 结构以便去重
                        if "summary" in entry:
                            s = entry["summary"]
                            s["all_keywords"] = set(s.get("all_keywords", []))
                            s["all_visual_objects"] = set(s.get("all_visual_objects", []))
                            s["all_labels"] = set(s.get("all_labels", []))
                        aggregated[entry['note_id']] = entry
            except Exception as e:
                utils.logger.warning(f"[Exporter.get_existing_ids] Warning: Failed to load existing aggregated data: {e}")

        for item in results:
            note_id = item['note_id']
            comment_id = item['comment_id']
            is_comment = comment_id != "0"
            
            if note_id not in aggregated:
                aggregated[note_id] = {
                    "note_id": note_id,
                    "top_id": item.get("top_id"),
                    "url": item.get("url"),
                    "post_content": "",
                    "post_analysis": {},
                    "post_author": "",
                    "created_at": "",
                    "images": [],
                    "comments": [],
                    "summary": {
                        "all_keywords": set(),
                        "all_visual_objects": set(),
                        "all_labels": set(),
                        "sentiment_distribution": {"正面": 0, "中性": 0, "负面": 0}
                    }
                }
            
            target = aggregated[note_id]
            
            # 评论 ID 去重检查
            if is_comment:
                existing_comment_ids = [c["comment_id"] for c in target["comments"]]
                if comment_id in existing_comment_ids:
                    continue # 如果评论已存在，跳过该条数据的聚合
            
            analysis = item.get("sentiment_analysis", {})
            sentiment = analysis.get("sentiment")
            
            # 更新情感分布统计
            if sentiment in target["summary"]["sentiment_distribution"]:
                target["summary"]["sentiment_distribution"][sentiment] += 1
            
            # 聚合关键词、视觉对象和标签 (去重)
            if item.get("keywords"):
                target["summary"]["all_keywords"].update([str(k) for k in item["keywords"] if k])
            if item.get("visual_objects"):
                target["summary"]["all_visual_objects"].update([str(o) for o in item["visual_objects"] if o])
            if item.get("labels"):
                target["summary"]["all_labels"].update([str(l) for l in item["labels"] if l])
            
            fg_sentiment = analysis.get("fine_grained_sentiment")
            if fg_sentiment:
                if isinstance(fg_sentiment, str):
                    target["summary"]["all_labels"].add(fg_sentiment)
                elif isinstance(fg_sentiment, dict):
                    # 如果模型输出错误格式，尝试提取值为 True 的键
                    for k, v in fg_sentiment.items():
                        if v is True:
                            target["summary"]["all_labels"].add(str(k))

            if not is_comment:
                # 填充主贴信息
                target["post_content"] = item.get("content", "")
                target["post_analysis"] = analysis
                target["post_author"] = item.get("author", "")
                target["created_at"] = item.get("created_at", "")
                target["images"] = item.get("image_paths", [])
            else:
                # 添加评论
                target["comments"].append({
                    "comment_id": item.get("comment_id"),
                    "content": item.get("content", ""),
                    "author": item.get("author", ""),
                    "created_at": item.get("created_at", ""),
                    "analysis": analysis
                })

        # 转换 set 为 list 以便序列化
        final_list = []
        for note_id, data in aggregated.items():
            data["summary"]["all_keywords"] = sorted(list(data["summary"]["all_keywords"]))
            data["summary"]["all_visual_objects"] = sorted(list(data["summary"]["all_visual_objects"]))
            data["summary"]["all_labels"] = sorted([str(l) for l in data["summary"]["all_labels"] if l])
            final_list.append(data)

        with open(agg_file, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, ensure_ascii=False, indent=2)
        
        # 如果当前不是备份文件且有日期，也同步备份一份到主文件(可选，取决于是否需要保留一份汇总)
        # 但根据用户要求，现在主要按日期存储，所以这里不需要冗余备份到 aggregated_display_data.json
        # 如果需要汇总，前端可以从 history 目录下读取所有文件并合并。

    def _format_entry(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Format a single item (post or comment) according to the user's schema."""
        analysis = item.get("analysis", {})
        
        # Combine image paths into content description if requested
        content = item.get("content", "")
        images = item.get("images", [])
        
        # Translate platform name
        raw_source = item.get("source", "unknown")
        source_name = PLATFORM_MAP.get(raw_source, raw_source)

        # 只有在检测到反讽时才在推理中体现相关说明
        irony_detected = analysis.get("irony_detected", False)
        reasoning = analysis.get("reasoning", "")
        
        # 确保 reasoning 是字符串，防止 AttributeError
        if isinstance(reasoning, dict):
             reasoning = json.dumps(reasoning, ensure_ascii=False)
        elif not isinstance(reasoning, str):
             reasoning = str(reasoning)

        if not irony_detected:
            # 如果没有反讽，清理推理过程中的反讽相关词汇，或者保持简洁
            reasoning = reasoning.split("，没有")[0].split(", no")[0]
        
        # 基础字段构建
        entry = {
            "top_id": item.get("top_id"),
            "note_id": item.get("note_id"),
            "comment_id": item.get("comment_id"),
            "content": content,
            "image_paths": images,
            "source": source_name,
            "author": item.get("author", ""),
            "created_at": item.get("created_at", ""),
            "url": item.get("url"),
            "ip_location": item.get("ip_location", "")
        }

        # 区分文章和评论插入统计字段（置于 sentiment_analysis 之前）
        if entry["comment_id"] == "0":
            entry["liked_count"] = item.get("liked_count", 0)
            entry["comments_count"] = item.get("comments_count", 0)
            entry["shared_count"] = item.get("shared_count", 0)
        else:
            entry["comment_like_count"] = item.get("comment_like_count", 0)
            entry["sub_comment_count"] = item.get("sub_comment_count", 0)
            entry["gender"] = item.get("gender", "")
            entry["parent_comment_id"] = item.get("parent_comment_id")

        # 插入核心分析字段
        entry["sentiment_analysis"] = {
            "sentiment": analysis.get("sentiment"),
            "fine_grained_sentiment": analysis.get("fine_grained_sentiment"),
            "intent": analysis.get("intent"),
            "irony_detected": irony_detected,
            "reasoning": reasoning
        }
        
        # 补充标签和视觉字段
        entry.update({
            "labels": analysis.get("sentiment_labels", [analysis.get("sentiment")]),
            "keywords": analysis.get("keywords", []),
            "visual_objects": analysis.get("objects", []),
            "ocr_text": analysis.get("ocr_text", "")
        })

        # 评论记录不需要 top_id
        if entry["comment_id"] != "0" and "top_id" in entry:
            del entry["top_id"]
            
        return entry
