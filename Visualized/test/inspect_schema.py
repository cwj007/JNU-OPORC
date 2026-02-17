import sqlite3

db_path = r'e:\JNU-OPORC\Visualized\cache\hotsearch.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='monitoring_tasks'")
result = cursor.fetchone()
if result:
    print(result[0])
else:
    print("Table not found")
conn.close()
