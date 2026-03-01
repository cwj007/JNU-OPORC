import sqlite3
import json
import os

db_path = r'e:\JNU-OPORC\Visualized\cache\hotsearch.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, title, reference_id, meta_data FROM alerts WHERE id = 3187")
    row = cursor.fetchone()
    if row:
        print(f"ID: {row['id']}")
        print(f"Title: {row['title']}")
        print(f"Reference ID: {row['reference_id']}")
        meta = json.loads(row['meta_data'])
        print(f"Meta Data: {json.dumps(meta, indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
