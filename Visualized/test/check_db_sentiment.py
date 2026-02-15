import sqlite3
import os

db_path = r'E:\JNU-OPORC\Transformers\cache\processed_ids.db'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- Content Sentiment Samples ---")
    cursor.execute("SELECT sentiment, COUNT(*) FROM content GROUP BY sentiment")
    for row in cursor.fetchall():
        print(row)
        
    print("\n--- Comments Sentiment Samples ---")
    cursor.execute("SELECT sentiment, COUNT(*) FROM comments GROUP BY sentiment")
    for row in cursor.fetchall():
        print(row)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
