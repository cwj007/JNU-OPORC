
import sqlite3

def list_tasks():
    conn = sqlite3.connect('Visualized/cache/hotsearch.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, keywords, platforms FROM monitoring_tasks")
    tasks = cursor.fetchall()
    for task in tasks:
        print(f"ID: {task['id']}, Name: {task['name']}, Keywords: {task['keywords']}, Platforms: {task['platforms']}")
    conn.close()

if __name__ == "__main__":
    list_tasks()
