import sqlite3
import json
import os

db_path = 'Visualized/cache/hotsearch.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT id, title, reference_id, user_id FROM alerts WHERE title LIKE '%单贴高危预警%' LIMIT 2")
for row in cur.fetchall():
    print(f"ID: {row['id']}")
    print(f"Title: {repr(row['title'])}")
    print(f"RefID: {repr(row['reference_id'])}")
    print(f"UserID: {row['user_id']}")
    print("-" * 20)

conn.close()
