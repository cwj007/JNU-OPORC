
import sys
import os
from pathlib import Path
import sqlite3

# Add project root to sys.path
BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))

from Visualized.api.database import TRANSFORMERS_DB_PATH

print(f"DB Path: {TRANSFORMERS_DB_PATH}")

try:
    conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
    cur = conn.cursor()
    
    # 1. 检查 content 表是否有 top_id 列
    cur.execute("PRAGMA table_info(content)")
    columns = {row[1] for row in cur.fetchall()}
    
    if "top_id" not in columns:
        print("Adding missing column top_id to table content...")
        try:
            cur.execute("ALTER TABLE content ADD COLUMN top_id TEXT")
            conn.commit()
            print("Column added successfully.")
        except Exception as e:
            print(f"Error adding column: {e}")
    else:
        print("Column top_id already exists in content table.")
        
    # 2. 从 processed_items 更新 top_id 到 content
    print("Migrating top_id data from processed_items to content...")
    
    # 使用 UPDATE JOIN (SQLite 语法支持)
    # SQLite 的 UPDATE FROM 语法在较新版本才支持。
    # 我们可以尝试使用子查询或者临时表。
    
    # 方法 1: 使用子查询 (标准 SQL)
    # UPDATE content SET top_id = (SELECT top_id FROM processed_items WHERE processed_items.note_id = content.note_id LIMIT 1) WHERE top_id IS NULL OR top_id = ''
    
    sql = """
        UPDATE content 
        SET top_id = (
            SELECT top_id 
            FROM processed_items 
            WHERE processed_items.note_id = content.note_id 
            AND processed_items.comment_id = '0'
            LIMIT 1
        )
        WHERE top_id IS NULL OR top_id = ''
    """
    
    cur.execute(sql)
    print(f"Updated {cur.rowcount} rows.")
    conn.commit()
    
    # 3. 验证更新结果
    cur.execute("SELECT COUNT(*) FROM content WHERE top_id IS NOT NULL AND top_id != ''")
    count = cur.fetchone()[0]
    print(f"Total rows with top_id: {count}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
