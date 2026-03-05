import sqlite3
db = r'e:\JNU-OPORC\MediaCrawler\database\sqlite_tables.db'
conn = sqlite3.connect(db)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print(f"Tables: {tables}")
for table in tables:
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [col[1] for col in cursor.fetchall()]
    print(f"Table {table}: {cols}")
    
    # Check for date columns and counts
    date_col = None
    if 'create_at' in cols: date_col = 'create_at'
    elif 'created_at' in cols: date_col = 'created_at'
    elif 'add_ts' in cols: date_col = 'add_ts'
    
    if date_col:
        # Get count for today (timestamp or string)
        # Try as timestamp (ms) first if it's an integer type
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        total = cursor.fetchone()[0]
        print(f"  - Total records in {table}: {total}")
conn.close()
