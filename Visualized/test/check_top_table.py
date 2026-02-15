
import sqlite3
from pathlib import Path
import sys

# Add project root to sys.path
BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))

from Visualized.api.database import TRANSFORMERS_DB_PATH

print(f"DB Path: {TRANSFORMERS_DB_PATH}")

try:
    conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
    cur = conn.cursor()
    
    # Check tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    print(f"Tables: {tables}")
    
    if 'top_topics' in tables:
        cur.execute("PRAGMA table_info(top_topics)")
        columns = [row[1] for row in cur.fetchall()]
        print(f"top_topics columns: {columns}")
    else:
        print("top_topics table does not exist.")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
