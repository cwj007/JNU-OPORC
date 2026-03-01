import sqlite3
import json
import os

db_path = r'e:\JNU-OPORC\Visualized\cache\hotsearch.db'
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, title, reference_id, meta_data FROM alerts ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row['id']}")
        print(f"Title: {row['title']}")
        print(f"Reference ID: {row['reference_id']}")
        meta = row['meta_data']
        if meta:
            try:
                meta_json = json.loads(meta)
                print(f"Meta Data Keys: {list(meta_json.keys())}")
            except:
                print("Meta Data: (Invalid JSON)")
        else:
            print("Meta Data: (Empty)")
        print("-" * 20)
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
