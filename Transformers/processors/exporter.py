import json
import os
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

class Exporter:
    def __init__(self, output_file: str):
        self.output_file = Path(output_file)
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
        
        # 字段升级逻辑
        cursor.execute("PRAGMA table_info(processed_items)")
        cols = [c[1] for c in cursor.fetchall()]
        
        # 动态添加缺失的字段
        new_fields = [
            ('sync_date', 'TEXT'),
            ('content', 'TEXT'),
            ('created_at', 'TEXT'),
            ('visual_objects', 'TEXT'),
            ('ocr_text', 'TEXT'),
            ('author', 'TEXT'),
            ('source', 'TEXT'),
            ('liked_count', 'INTEGER'),
            ('comments_count', 'INTEGER'),
            ('shared_count', 'INTEGER'),
            ('gender', 'TEXT'),
            ('ip_location', 'TEXT'),
            ('parent_comment_id', 'TEXT'),
            ('top_id', 'TEXT')
        ]
        
        for field_name, field_type in new_fields:
            if field_name not in cols:
                cursor.execute(f'ALTER TABLE processed_items ADD COLUMN {field_name} {field_type}')
        
        conn.commit()
        conn.close()

    def get_existing_ids(self) -> set:
        """从 SQLite 数据库中极速获取所有已处理的 ID。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT unique_id FROM processed_items')
        ids = {row[0] for row in cursor.fetchall()}
        conn.close()
        return ids

    def _is_id_processed(self, unique_id: str) -> bool:
        """在数据库中检查单条 ID 是否存在（极速查询）。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM processed_items WHERE unique_id = ?', (unique_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def _mark_ids_as_processed(self, entries_for_db: List[tuple]):
        """批量将 ID 和分析结果存入数据库。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.executemany('''
            INSERT OR REPLACE INTO processed_items (
                unique_id, note_id, comment_id, top_id, data_date, sync_date, created_at, content,
                sentiment, intent, keywords, ip_location, visual_objects, 
                ocr_text, author, source, liked_count, comments_count, 
                shared_count, gender, parent_comment_id
            ) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', entries_for_db)
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
                print(f"  [写入错误] 后台线程异常: {e}")

    def _process_export_task(self, analyzed_data: List[Dict[str, Any]], append: bool, use_lock: bool):
        """实际的写入逻辑：格式化、去重、存库、写文件。"""
        formatted_results = []
        data_date = analyzed_data[0].get("data_date")
        
        # 1. 过滤已存在的 ID (使用 SQLite 极速查询)
        valid_entries = []
        db_entries = []
        top_entries = {} # top_id -> top_name
        sync_date = datetime.now().strftime("%Y-%m-%d")
        
        for item in analyzed_data:
            entry = self._format_entry(item)
            note_id = str(entry.get('note_id'))
            comment_id = str(entry.get('comment_id', '0'))
            unique_id = f"{note_id}_{comment_id}"
            
            if not self._is_id_processed(unique_id):
                valid_entries.append(entry)
                # 提取统计字段
                sentiment = str(entry.get("sentiment_analysis", {}).get("sentiment", "Unknown"))
                intent = str(entry.get("sentiment_analysis", {}).get("intent", "Unknown"))
                keywords = json.dumps(entry.get("keywords", []), ensure_ascii=False)
                ip_location = str(entry.get("ip_location", ""))
                top_id = str(entry.get("top_id", ""))
                top_name = entry.get("top_name")
                created_at = str(entry.get("created_at", ""))
                content = str(entry.get("content", ""))
                visual_objects = json.dumps(entry.get("visual_objects", []), ensure_ascii=False)
                ocr_text = str(entry.get("ocr_text", ""))
                author = str(entry.get("author", ""))
                source = str(entry.get("source", ""))
                
                # 区分文章和评论的计数
                liked_count = entry.get("liked_count") or entry.get("comment_like_count") or 0
                comments_count = entry.get("comments_count") or entry.get("sub_comment_count") or 0
                shared_count = entry.get("shared_count") or 0
                gender = str(entry.get("gender", ""))
                parent_comment_id = str(entry.get("parent_comment_id", ""))
                
                db_entries.append((
                    unique_id, note_id, comment_id, top_id, str(data_date or ""), sync_date, created_at, content,
                    sentiment, intent, keywords, ip_location, visual_objects, 
                    ocr_text, author, source, liked_count, comments_count, 
                    shared_count, gender, parent_comment_id
                ))

                # 记录 top_topics
                if top_id and top_id != "None":
                    if top_name:
                        top_entries[top_id] = top_name
                    else:
                        # 如果没有 top_name，尝试从 top_id 解码
                        top_entries[top_id] = unquote(top_id)

        if not valid_entries:
            return

        # 2. 写入 JSONL 文件 (使用文件锁保护多进程安全)
        mode = 'a' if append else 'w'
        if use_lock:
            lock_path = f"{self.output_file}.lock"
            with FileLock(lock_path):
                self._write_to_files(valid_entries, data_date, mode)
        else:
            self._write_to_files(valid_entries, data_date, mode)

        # 3. 写入数据库索引
        self._mark_ids_as_processed(db_entries)
        
        # 4. 写入 top_topics 表
        if top_entries:
            self._update_top_topics(top_entries)
        
        # 5. 输出存储日志
        print(f"  └─ [存储] {len(valid_entries)} 条新记录已异步同步 (SQLite 索引已更新)")

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

    def _write_to_files(self, valid_entries, data_date, mode):
        """物理写入文件：通过临时文件原子性替换，防止写入中断导致损坏。"""
        # 写入主文件
        temp_main = f"{self.output_file}.tmp"
        try:
            # 1. 写入临时文件
            with open(temp_main, 'w', encoding='utf-8') as f:
                for entry in valid_entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            # 2. 追加到正式文件
            with open(self.output_file, 'a', encoding='utf-8') as f:
                with open(temp_main, 'r', encoding='utf-8') as tf:
                    f.write(tf.read())
            
            # 3. 写入历史备份
            if data_date:
                history_file = HISTORICAL_LABELED_DIR / f"labeled_results_{data_date}.jsonl"
                with open(history_file, 'a', encoding='utf-8') as f:
                    with open(temp_main, 'r', encoding='utf-8') as tf:
                        f.write(tf.read())
            
            # 4. 更新聚合 JSON (针对前端展示)
            self._export_aggregated_data(valid_entries, data_date, True)
            
        finally:
            if os.path.exists(temp_main):
                os.remove(temp_main)

    def close(self):
        """关闭 Exporter，确保所有数据写完。"""
        self.stop_event.set()
        if self.write_thread.is_alive():
            self.write_thread.join()

    def _export_aggregated_data(self, results: List[Dict[str, Any]], data_date: str, append: bool):
        """将数据按文章聚合，并对标签/关键词进行去重，生成前端易用的 JSON。"""
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
                print(f"Warning: Failed to load existing aggregated data: {e}")

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
                target["post_content"] = item["content"]
                target["post_analysis"] = analysis
                target["post_author"] = item["author"]
                target["created_at"] = item["created_at"]
                target["images"] = item["image_paths"]
            else:
                # 添加评论
                target["comments"].append({
                    "comment_id": item["comment_id"],
                    "content": item["content"],
                    "author": item["author"],
                    "created_at": item["created_at"],
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
        
        # 如果有日期，备份一份聚合数据
        if data_date:
            history_agg = HISTORICAL_LABELED_DIR / f"aggregated_{data_date}.json"
            with open(history_agg, 'w', encoding='utf-8') as f:
                json.dump(final_list, f, ensure_ascii=False, indent=2)

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
