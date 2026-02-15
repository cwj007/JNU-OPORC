
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

cur.execute("SELECT comment_id, COUNT(*) FROM processed_items WHERE top_id = ? GROUP BY comment_id", (target_q,))
rows = cur.fetchall()
print("Comment ID distribution:")
for r in rows:
    print(f"  id='{r[0]}': {r[1]}")

conn.close()
