import sqlite3
from pathlib import Path

# Path from database.py logic
db_path = Path('Transformers/cache/processed_ids.db')
if not db_path.exists():
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('SELECT note_id, title FROM content WHERE note_id = "QqCr26eNO"')
print(cur.fetchone())
conn.close()
