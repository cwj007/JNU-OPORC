
import sqlite3
from datetime import datetime

db_path = r"e:\JNU-OPORC\Transformers\cache\processed_ids.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

today = datetime.now().strftime("%Y-%m-%d")
print(f"Checking for date: {today}")

try:
    cursor.execute("SELECT count(*) FROM content WHERE sync_date = ?", (today,))
    content_count = cursor.fetchone()[0]
    print(f"Content count for today: {content_count}")

    cursor.execute("SELECT count(*) FROM comments WHERE sync_date = ?", (today,))
    comment_count = cursor.fetchone()[0]
    print(f"Comment count for today: {comment_count}")

    # Check distinct sync_dates
    cursor.execute("SELECT DISTINCT sync_date FROM content ORDER BY sync_date DESC LIMIT 5")
    dates = cursor.fetchall()
    print("Recent sync_dates in content:", dates)
    
    # Check if there are any records with today's created_at but different sync_date
    cursor.execute("SELECT count(*) FROM content WHERE created_at LIKE ?", (f"{today}%",))
    created_today_count = cursor.fetchone()[0]
    print(f"Content created_at today: {created_today_count}")

except Exception as e:
    print(f"Error: {e}")

conn.close()
