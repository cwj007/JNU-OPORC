
import sys
import os
from pathlib import Path
import sqlite3

BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))
from Visualized.api.database import TRANSFORMERS_DB_PATH

try:
    conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
    cur = conn.cursor()
    
    print("Creating index on content(top_id)...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_content_top_id ON content(top_id)")
    
    print("Creating index on content(title)...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_content_title ON content(title)")
    
    print("Creating index on content(source)...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_content_source ON content(source)")
    
    print("Creating index on processed_items(top_id)...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_items_top_id ON processed_items(top_id)")
    
    print("Creating index on content(note_id)...") # Usually primary key but good to ensure
    cur.execute("CREATE INDEX IF NOT EXISTS idx_content_note_id ON content(note_id)")
    
    conn.commit()
    conn.close()
    print("Indices created successfully.")
except Exception as e:
    print(f"Error: {e}")
