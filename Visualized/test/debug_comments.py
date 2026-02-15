
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
    
    # 1. 随机获取一个有评论的文章
    print("\nChecking for articles with comments...")
    cur.execute("""
        SELECT c.note_id, c.title, COUNT(cm.id) as comment_count 
        FROM content c 
        LEFT JOIN comments cm ON c.note_id = cm.note_id 
        GROUP BY c.note_id 
        HAVING comment_count > 0 
        LIMIT 1
    """)
    row = cur.fetchone()
    
    if row:
        note_id = row['note_id']
        print(f"Found article: {row['title']} (note_id: {note_id}) with {row['comment_count']} comments")
        
        # 2. 检查该文章在 processed_items 中的 top_id
        cur.execute("SELECT top_id FROM processed_items WHERE note_id = ?", (note_id,))
        p_rows = cur.fetchall()
        print(f"Processed items top_ids for this note_id: {[r['top_id'] for r in p_rows]}")
        
        # 3. 检查 comments 表中的数据样例
        cur.execute("SELECT * FROM comments WHERE note_id = ? LIMIT 1", (note_id,))
        comment = cur.fetchone()
        print(f"Sample comment: {dict(comment)}")
        
    else:
        print("No articles with comments found via join.")
        
        # Check raw counts
        cur.execute("SELECT COUNT(*) FROM content")
        print(f"Total content: {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(*) FROM comments")
        print(f"Total comments: {cur.fetchone()[0]}")
        
        # Check one comment to see its note_id
        cur.execute("SELECT note_id FROM comments LIMIT 1")
        res = cur.fetchone()
        if res:
            c_note_id = res[0]
            print(f"Comment exists for note_id: {c_note_id}")
            # Check if this note_id exists in content
            cur.execute("SELECT * FROM content WHERE note_id = ?", (c_note_id,))
            if cur.fetchone():
                print("And this note_id exists in content table.")
            else:
                print("BUT this note_id does NOT exist in content table!")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
