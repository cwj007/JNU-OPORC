import sqlite3
import os

db_path = r'e:\JNU-OPORC\Transformers\cache\processed_ids.db'
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("PRAGMA table_info(content)")
    cols = cursor.fetchall()
    print("Columns in 'content' table:")
    for col in cols:
        print(col)
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
