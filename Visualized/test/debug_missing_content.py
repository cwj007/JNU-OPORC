
import sys
import os
from pathlib import Path
import sqlite3

# Add project root to sys.path
BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))

from Visualized.api.database import TRANSFORMERS_DB_PATH

try:
    conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
    cur = conn.cursor()
    
    target_q = "%E6%83%85%E4%BA%BA%E8%8A%82"
    print(f"Checking for top_id: {target_q}")
    
    # 1. Get note_ids from processed_items
    cur.execute("SELECT note_id FROM processed_items WHERE top_id = ? AND comment_id = '0'", (target_q,))
    p_ids = [row[0] for row in cur.fetchall()]
    print(f"Found {len(p_ids)} note_ids in processed_items (comment_id=0)")
    if p_ids:
        print(f"Sample IDs: {p_ids[:5]}")
        
        # 2. Check if they exist in content
        # Use IN clause
        placeholders = ','.join(['?'] * len(p_ids))
        cur.execute(f"SELECT note_id FROM content WHERE note_id IN ({placeholders})", p_ids)
        c_ids = [row[0] for row in cur.fetchall()]
        print(f"Found {len(c_ids)} matching note_ids in content table")
        
        # 3. Check one that is missing (if any)
        missing = set(p_ids) - set(c_ids)
        if missing:
            print(f"Missing IDs count: {len(missing)}")
            print(f"Sample missing ID: {list(missing)[0]}")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
