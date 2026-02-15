import sqlite3
import os

db_path = r'E:\JNU-OPORC\Transformers\cache\processed_ids.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check content
    print("Checking content table...")
    cursor.execute("SELECT note_id, title, content FROM content LIMIT 1")
    row = cursor.fetchone()
    if row:
        print(f"Found article: note_id={row[0]}, title={row[1]}")
        
        # Check comments for this note_id
        cursor.execute("SELECT comment_id, content FROM comments WHERE note_id = ? LIMIT 1", (row[0],))
        comment = cursor.fetchone()
        if comment:
            print(f"Found comment: comment_id={comment[0]}, content={comment[1]}")
        else:
            print("No comments found for this article.")
    else:
        print("No articles found in content table.")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
