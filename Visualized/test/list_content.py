import sqlite3
from pathlib import Path

db_path = Path('Transformers/cache/processed_ids.db')
if not db_path.exists():
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('SELECT note_id, title, created_at FROM content LIMIT 5')
for row in cur.fetchall():
    print(row)
conn.close()
