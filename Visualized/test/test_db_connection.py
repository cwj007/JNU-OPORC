import os
import sys
import sqlite3
from pathlib import Path

# Setup paths
current_dir = Path(os.getcwd())
project_root = current_dir.parent
if current_dir.name != "Visualized":
    if (current_dir / "Visualized").exists():
        project_root = current_dir
        current_dir = project_root / "Visualized"

visualized_dir = project_root / "Visualized"
transformers_dir = project_root / "Transformers"

transformers_db = transformers_dir / "cache" / "processed_ids.db"

print(f"Checking Transformers DB at: {transformers_db}")
if transformers_db.exists():
    try:
        conn = sqlite3.connect(transformers_db)
        cursor = conn.cursor()
        
        # Check content table schema with types
        cursor.execute("PRAGMA table_info(content)")
        columns = cursor.fetchall()
        print(f"Columns in content table: {[(col[1], col[2]) for col in columns]}")

        # Check comments table schema with types
        cursor.execute("PRAGMA table_info(comments)")
        columns = cursor.fetchall()
        print(f"Columns in comments table: {[(col[1], col[2]) for col in columns]}")
        
        conn.close()
    except Exception as e:
        print(f"Error connecting to Transformers DB: {e}")
else:
    print("Transformers DB does NOT exist.")
