import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cache', 'hotsearch.db')

def check_and_create_table():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_platform_follows'")
    if cursor.fetchone():
        print("Table 'user_platform_follows' already exists.")
    else:
        print("Creating 'user_platform_follows' table...")
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_platform_follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, platform_id)
        )
        ''')
        conn.commit()
        print("Table created successfully.")
    
    conn.close()

if __name__ == "__main__":
    check_and_create_table()
