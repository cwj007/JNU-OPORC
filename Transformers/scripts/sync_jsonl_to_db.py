import json
import sqlite3
import os
import sys
from pathlib import Path

# 设置路径
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(BASE_DIR))

from Transformers.config import CACHE_DIR, LABELED_DATA_FILE
from Transformers import utils

JSONL_FILE = LABELED_DATA_FILE
DB_FILE = CACHE_DIR / "processed_ids.db"

def sync_ids():
    if not JSONL_FILE.exists():
        utils.logger.error(f"[sync_jsonl_to_db.sync_ids] 错误: 找不到文件 {JSONL_FILE}")
        return

    utils.logger.info(f"[sync_jsonl_to_db.sync_ids] 正在从 {JSONL_FILE.name} 同步 ID 到 SQLite...")
    
    # 连接数据库
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 确保表存在且字段完整
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_items (
            unique_id TEXT PRIMARY KEY,
            data_date TEXT,
            sentiment TEXT,
            intent TEXT
        )
    ''')
    # 字段升级逻辑
    cursor.execute("PRAGMA table_info(processed_items)")
    cols = [c[1] for c in cursor.fetchall()]
    if 'sentiment' not in cols:
        cursor.execute('ALTER TABLE processed_items ADD COLUMN sentiment TEXT')
    if 'intent' not in cols:
        cursor.execute('ALTER TABLE processed_items ADD COLUMN intent TEXT')
    
    count = 0
    duplicate_count = 0
    
    with open(JSONL_FILE, 'r', encoding='utf-8') as f:
        batch_entries = []
        for line in f:
            try:
                item = json.loads(line.strip())
                note_id = str(item.get("note_id", ""))
                comment_id = str(item.get("comment_id", "0"))
                unique_id = f"{note_id}_{comment_id}"
                
                # 提取日期
                created_at = item.get("created_at", "")
                data_date = created_at.split(" ")[0] if created_at else "unknown"
                
                # 提取情感统计字段
                analysis = item.get("sentiment_analysis", {})
                sentiment = analysis.get("sentiment", "Unknown")
                intent = analysis.get("intent", "Unknown")
                
                batch_entries.append((unique_id, data_date, sentiment, intent))
                
                # 每 500 条执行一次批量插入
                if len(batch_entries) >= 500:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO processed_items (unique_id, data_date, sentiment, intent) 
                        VALUES (?, ?, ?, ?)
                    ''', batch_entries)
                    count += cursor.rowcount
                    batch_entries = []
                    utils.logger.info(f"[sync_jsonl_to_db.sync_ids] 已处理 {count} 条...")
                    
            except Exception as e:
                utils.logger.error(f"[sync_jsonl_to_db.sync_ids] 处理行时出错: {e}")
        
        # 处理剩余的记录
        if batch_entries:
            cursor.executemany('''
                INSERT OR REPLACE INTO processed_items (unique_id, data_date, sentiment, intent) 
                VALUES (?, ?, ?, ?)
            ''', batch_entries)
            count += cursor.rowcount

    conn.commit()
    conn.close()
    
    utils.logger.info("="*40)
    utils.logger.info(f"[sync_jsonl_to_db.sync_ids] 同步完成！")
    utils.logger.info(f"[sync_jsonl_to_db.sync_ids] 总计扫描行数: {count + duplicate_count}")
    utils.logger.info(f"[sync_jsonl_to_db.sync_ids] 新增同步到 DB: {count}")
    utils.logger.info(f"[sync_jsonl_to_db.sync_ids] 跳过已存在 ID: {duplicate_count}")
    utils.logger.info("="*40)

if __name__ == "__main__":
    sync_ids()
