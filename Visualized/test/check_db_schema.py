
import sqlite3

db_path = r"e:\JNU-OPORC\Transformers\cache\processed_ids.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(processed_items)")
columns = cursor.fetchall()
print(f"Total columns: {len(columns)}")
for col in columns:
    print(col)

conn.close()
