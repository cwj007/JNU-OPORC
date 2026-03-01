import sqlite3
import os
from pathlib import Path

db_path = 'e:/JNU-OPORC/Transformers/cache/processed_ids.db'
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if FTS tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'")
    fts_tables = [t[0] for t in cursor.fetchall()]
    print(f"FTS tables found: {fts_tables}")

    if 'content_fts' in fts_tables:
        cursor.execute('SELECT COUNT(*) FROM content_fts')
        print(f'content_fts count: {cursor.fetchone()[0]}')
    
    if 'comments_fts' in fts_tables:
        cursor.execute('SELECT COUNT(*) FROM comments_fts')
        print(f'comments_fts count: {cursor.fetchone()[0]}')
    
    # Check triggers
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
    triggers = [t[0] for t in cursor.fetchall()]
    print(f"Triggers found: {triggers}")

    # Check some content
    if 'content_fts' in fts_tables:
        cursor.execute("SELECT rowid, title FROM content_fts LIMIT 5")
        print(f"Sample FTS content: {cursor.fetchall()}")

except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
