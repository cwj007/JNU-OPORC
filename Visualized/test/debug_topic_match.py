
import sys
import os
from pathlib import Path
import sqlite3
from urllib.parse import unquote

# Add project root to sys.path
BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))

from Visualized.api.database import TRANSFORMERS_DB_PATH

print(f"DB Path: {TRANSFORMERS_DB_PATH}")

try:
    conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
    cur = conn.cursor()
    
    # 1. 检查 processed_items 中的 top_id 样本
    print("\nSample top_ids from processed_items:")
    cur.execute("SELECT DISTINCT top_id FROM processed_items LIMIT 10")
    p_tops = [row[0] for row in cur.fetchall()]
    for t in p_tops:
        print(f"  {t} (decoded: {unquote(t)})")
        
    # 2. 检查 top_topics 中的 top_id 样本
    print("\nSample top_ids from top_topics:")
    cur.execute("SELECT top_id, top_name FROM top_topics LIMIT 10")
    t_tops = cur.fetchall()
    for t in t_tops:
        print(f"  {t[0]} (name: {t[1]})")
        
    # 3. 检查特定的话题 '情人节'
    target_q = "%E6%83%85%E4%BA%BA%E8%8A%82"
    print(f"\nChecking for specific topic: {target_q} (情人节)")
    
    cur.execute("SELECT COUNT(*) FROM processed_items WHERE top_id = ?", (target_q,))
    count_p = cur.fetchone()[0]
    print(f"  In processed_items: {count_p}")
    
    cur.execute("SELECT * FROM top_topics WHERE top_id = ?", (target_q,))
    row_t = cur.fetchone()
    if row_t:
        print(f"  In top_topics: Found (name: {row_t[1]})")
    else:
        print("  In top_topics: Not Found")
        
    # 4. 检查关联查询是否能找到
    print("\nChecking JOIN query result:")
    query = """
        SELECT COUNT(*) 
        FROM content c
        JOIN processed_items p ON c.note_id = p.note_id
        WHERE p.top_id = ?
    """
    cur.execute(query, (target_q,))
    count_join = cur.fetchone()[0]
    print(f"  Content found via JOIN: {count_join}")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
