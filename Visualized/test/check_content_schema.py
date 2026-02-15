
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
    cur.execute("PRAGMA table_info(content)")
    columns = [row[1] for row in cur.fetchall()]
    print(f"Content table columns: {columns}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
