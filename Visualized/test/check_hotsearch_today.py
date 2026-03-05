import sqlite3
from datetime import datetime

db = r'e:\JNU-OPORC\Visualized\cache\hotsearch.db'
conn = sqlite3.connect(db)
cursor = conn.cursor()

today = datetime.now().strftime("%Y-%m-%d")
print(f"Checking alerts for today: {today}")

# Check alerts
cursor.execute("SELECT count(*) FROM alerts WHERE time LIKE ?", (f"{today}%",))
print(f"Alerts created today: {cursor.fetchone()[0]}")

# Check hot_search_data
cursor.execute("SELECT count(*) FROM hot_search_data WHERE fetch_time LIKE ?", (f"{today}%",))
print(f"Hot search records fetched today: {cursor.fetchone()[0]}")

# Check notifications_log
cursor.execute("SELECT count(*) FROM notifications_log WHERE sent_at LIKE ?", (f"{today}%",))
print(f"Notifications sent today: {cursor.fetchone()[0]}")

conn.close()
