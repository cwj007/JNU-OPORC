
import sys
import os
from pathlib import Path
import sqlite3

BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))
from Visualized.api.database import TRANSFORMERS_DB_PATH

conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
cur = conn.cursor()
target_q = "%E6%83%85%E4%BA%BA%E8%8A%82"

print(f"Checking for note_ids associated with comments in topic: {target_q}")

# 1. Get DISTINCT note_ids from processed_items where top_id matches
cur.execute("SELECT DISTINCT note_id FROM processed_items WHERE top_id = ?", (target_q,))
p_ids = [row[0] for row in cur.fetchall()]
print(f"Found {len(p_ids)} unique note_ids in processed_items for this topic")

if p_ids:
    # 2. Check if these note_ids exist in content table
    placeholders = ','.join(['?'] * len(p_ids))
    cur.execute(f"SELECT note_id FROM content WHERE note_id IN ({placeholders})", p_ids)
    c_ids = [row[0] for row in cur.fetchall()]
    print(f"Found {len(c_ids)} matching note_ids in content table")
    
    if len(c_ids) == 0:
        print("CRITICAL: None of the note_ids exist in content table!")
        print("This means we have comments processed for this topic, but the parent articles are missing from content table.")

conn.close()
