import sqlite3
from pathlib import Path

# Calculate DB path
SCRIPT_DIR = Path(__file__).parent
VISUALIZED_DIR = SCRIPT_DIR.parent
CACHE_DIR = VISUALIZED_DIR / "cache"
HOTSEARCH_DB_PATH = CACHE_DIR / "hotsearch.db"

def inspect_db():
    conn = sqlite3.connect(HOTSEARCH_DB_PATH)
    cur = conn.cursor()
    
    print(f"Inspecting table 'users' in {HOTSEARCH_DB_PATH}")
    cur.execute("PRAGMA table_info(users)")
    columns = cur.fetchall()
    
    if not columns:
        print("Table 'users' does not exist.")
    else:
        print("Columns:")
        for col in columns:
            print(col)

    print("\nInspecting table 'alerts'")
    cur.execute("PRAGMA table_info(alerts)")
    columns = cur.fetchall()
    for col in columns:
        print(col)

    print("\nInspecting table 'alert_rules'")
    cur.execute("PRAGMA table_info(alert_rules)")
    columns = cur.fetchall()
    for col in columns:
        print(col)
            
    conn.close()

if __name__ == "__main__":
    inspect_db()
