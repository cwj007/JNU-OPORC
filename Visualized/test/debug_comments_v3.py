
import sys
import os
from pathlib import Path
import sqlite3
import json

# Add project root to sys.path
BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))

from Visualized.api.database import TRANSFORMERS_DB_PATH

print(f"DB Path: {TRANSFORMERS_DB_PATH}")

try:
    conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. 查找有评论的文章，并关联 processed_items 查看 top_id
    print("\nChecking for articles with comments and their top_ids...")
    cur.execute("""
        SELECT c.note_id, c.title, p.top_id, COUNT(cm.comment_id) as comment_count 
        FROM content c 
        JOIN processed_items p ON c.note_id = p.note_id
        LEFT JOIN comments cm ON c.note_id = cm.note_id 
        GROUP BY c.note_id 
        HAVING comment_count > 0 
        LIMIT 5
    """)
    rows = cur.fetchall()
    
    if rows:
        for row in rows:
            print(f"Article: {row['title'][:20]}... | note_id: {row['note_id']} | top_id: {row['top_id']} | comments: {row['comment_count']}")
            
            # Check comment sample
            cur.execute("SELECT * FROM comments WHERE note_id = ? LIMIT 1", (row['note_id'],))
            cm = cur.fetchone()
            if cm:
                print(f"  Sample comment id: {cm['comment_id']}")
    else:
        print("No articles found with comments via this join.")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
