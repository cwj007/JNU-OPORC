
import sqlite3
import os

# Define paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "cache", "hotsearch.db")

def update_schema():
    print(f"Checking database at {DB_PATH}...")
    
    if not os.path.exists(DB_PATH):
        print("Database not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        # 1. Check alert_rules table
        print("Checking alert_rules table...")
        cur.execute("PRAGMA table_info(alert_rules)")
        columns = [col[1] for col in cur.fetchall()]
        if 'user_id' not in columns:
            print("Adding user_id column to alert_rules...")
            cur.execute("ALTER TABLE alert_rules ADD COLUMN user_id INTEGER")
        else:
            print("alert_rules already has user_id.")

        # 2. Check alerts table
        print("Checking alerts table...")
        cur.execute("PRAGMA table_info(alerts)")
        columns = [col[1] for col in cur.fetchall()]
        if 'user_id' not in columns:
            print("Adding user_id column to alerts...")
            cur.execute("ALTER TABLE alerts ADD COLUMN user_id INTEGER")
        else:
            print("alerts already has user_id.")

        # 3. Check monitoring_tasks table
        print("Checking monitoring_tasks table...")
        cur.execute("PRAGMA table_info(monitoring_tasks)")
        columns = [col[1] for col in cur.fetchall()]
        if 'user_id' not in columns:
            print("Adding user_id column to monitoring_tasks...")
            cur.execute("ALTER TABLE monitoring_tasks ADD COLUMN user_id INTEGER")
        else:
            print("monitoring_tasks already has user_id.")
            
        # 4. Check users table for email and email_notify_enabled
        print("Checking users table...")
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        if 'email' not in columns:
            print("Adding email column to users...")
            cur.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if 'email_notify_enabled' not in columns:
            print("Adding email_notify_enabled column to users...")
            cur.execute("ALTER TABLE users ADD COLUMN email_notify_enabled INTEGER DEFAULT 1")
            
        conn.commit()
        print("Schema update completed successfully.")

    except Exception as e:
        print(f"Error updating schema: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    update_schema()
