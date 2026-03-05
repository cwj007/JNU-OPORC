from datetime import datetime
import sqlite3

print(f"Current System Time: {datetime.now()}")
today = datetime.now().strftime("%Y-%m-%d")

db_path = r"e:\JNU-OPORC\Transformers\cache\processed_ids.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print(f"Checking data with created_at starting with: {today}")

try:
    # Check content
    cursor.execute("SELECT count(*) FROM content WHERE created_at LIKE ?", (f"{today}%",))
    content_count = cursor.fetchone()[0]
    print(f"Content records created today: {content_count}")

    # Check comments
    cursor.execute("SELECT count(*) FROM comments WHERE created_at LIKE ?", (f"{today}%",))
    comment_count = cursor.fetchone()[0]
    print(f"Comment records created today: {comment_count}")

    # Check some samples to see the format of created_at
    cursor.execute("SELECT created_at FROM content ORDER BY created_at DESC LIMIT 5")
    samples = cursor.fetchall()
    print(f"Sample created_at from content: {samples}")

except Exception as e:
    print(f"Error: {e}")

conn.close()
