from datetime import datetime, timedelta
import sqlite3

db_path = r"e:\JNU-OPORC\Transformers\cache\processed_ids.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Past 24 hours
start_time = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
print(f"Current System Time: {datetime.now()}")
print(f"Checking for records since: {start_time}")

try:
    # Check content
    cursor.execute("SELECT count(*) FROM content WHERE created_at >= ?", (start_time,))
    content_count = cursor.fetchone()[0]
    print(f"Content records in past 24h: {content_count}")

    # Check comments
    cursor.execute("SELECT count(*) FROM comments WHERE created_at >= ?", (start_time,))
    comment_count = cursor.fetchone()[0]
    print(f"Comment records in past 24h: {comment_count}")

    # Total
    print(f"Total new records (content + comments): {content_count + comment_count}")

except Exception as e:
    print(f"Error: {e}")

conn.close()
