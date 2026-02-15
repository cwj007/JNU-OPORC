
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
        SELECT c.note_id, c.title, p.top_id, COUNT(cm.id) as comment_count 
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
                print(f"  Sample comment: {dict(cm)}")
    else:
        print("No articles found with comments via this join.")
        
        # Debug: Check processed_items note_ids vs content note_ids
        cur.execute("SELECT note_id FROM processed_items LIMIT 5")
        p_ids = [r[0] for r in cur.fetchall()]
        print(f"Processed items note_ids: {p_ids}")
        
        cur.execute("SELECT note_id FROM content WHERE note_id IN ({})".format(','.join(['?']*len(p_ids))), p_ids)
        c_ids = [r[0] for r in cur.fetchall()]
        print(f"Matching content note_ids: {c_ids}")
        
        cur.execute("SELECT note_id FROM comments WHERE note_id IN ({})".format(','.join(['?']*len(p_ids))), p_ids)
        cm_ids = [r[0] for r in cur.fetchall()]
        print(f"Matching comment note_ids: {cm_ids}")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
