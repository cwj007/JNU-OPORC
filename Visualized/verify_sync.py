import sqlite3
from pathlib import Path

DB_PATH = Path(r"e:\JNU-OPORC\Transformers\cache\processed_ids.db")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("--- Checking new fields ---")
cursor.execute("""
    SELECT note_id, comment_id, visual_objects, ocr_text, author, liked_count, gender 
    FROM processed_items 
    WHERE visual_objects != '[]' OR ocr_text != '' 
    LIMIT 5
""")
rows = cursor.fetchall()
for row in rows:
    print(f"ID: {row[0]}_{row[1]}")
    print(f"Author: {row[4]}, Liked: {row[5]}, Gender: {row[6]}")
    print(f"Visual Objects: {row[2][:100]}...")
    print(f"OCR: {row[3][:100]}...")
    print("-" * 20)

conn.close()
