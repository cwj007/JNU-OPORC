
import os
import re
import sys
import sqlite3
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime

# Add project root to sys.path
BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))

from Visualized.api.database import TRANSFORMERS_DB_PATH

SOURCE_DIR = Path(r"e:\JNU-OPORC\MediaCrawler\source\weibo\specified_ids")

print(f"Scanning directory: {SOURCE_DIR}")
print(f"Target DB: {TRANSFORMERS_DB_PATH}")

def parse_file_time(file_path):
    """
    从文件路径解析时间
    Example: ...\20260214\12时32分.txt
    Returns: datetime object or None
    """
    try:
        # Parent dir is date: YYYYMMDD
        date_str = file_path.parent.name
        # Filename is time: HH时MM分.txt
        time_str = file_path.stem
        
        # Clean time str
        if "时" in time_str and "分" in time_str:
            time_str = time_str.replace("时", ":").replace("分", "")
        
        full_str = f"{date_str} {time_str}"
        # Try parsing
        dt = datetime.strptime(full_str, "%Y%m%d %H:%M")
        return dt
    except Exception as e:
        # print(f"  Warning: Could not parse time for {file_path}: {e}")
        return None

def process_files():
    conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
    cur = conn.cursor()
    
    # Ensure table exists (double check)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS top_topics (
            top_id TEXT PRIMARY KEY,
            top_name TEXT,
            created_at TEXT
        )
    ''')
    
    # Collect all txt files
    files = []
    for root, dirs, filenames in os.walk(SOURCE_DIR):
        for f in filenames:
            if f.endswith(".txt"):
                files.append(Path(root) / f)
    
    # Sort files by time (oldest first) to ensure created_at is the earliest
    files_with_time = []
    for f in files:
        dt = parse_file_time(f)
        if dt:
            files_with_time.append((f, dt))
        else:
            # Fallback: use mtime
            files_with_time.append((f, datetime.fromtimestamp(os.path.getmtime(f))))
    
    files_with_time.sort(key=lambda x: x[1])
    
    print(f"Found {len(files_with_time)} files to process.")
    
    count_new = 0
    count_skipped = 0
    
    for file_path, dt in files_with_time:
        created_at_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Find all Top URLs
            # Pattern: Top URL: https://s.weibo.com/weibo?q=...
            urls = re.findall(r'Top URL: (https?://[^\s\n]+)', content)
            
            for url in urls:
                try:
                    parsed = urlparse(url)
                    qs = parse_qs(parsed.query)
                    
                    if 'q' in qs:
                        # q is a list, take first
                        raw_q = qs['q'][0]
                        # In parse_qs, it might automatically decode percent-encoding?
                        # No, parse_qs decodes keys and values. 
                        # Wait, parse_qs DOES decode percent-encoded values by default.
                        # But we need the RAW encoded value for top_id to match processed_items logic?
                        # Let's check how processed_items stores it.
                        # In migrate_top_id.py logs:
                        # top_id: %23%E4%B8%AD%E6%88%8F%23
                        # This looks like it is URL encoded.
                        
                        # However, parse_qs returns DECODED string.
                        # We need to re-encode it OR parse manually.
                        # Manual parsing is safer to preserve exact original encoding.
                        
                        # Extract q parameter manually from query string
                        query_str = parsed.query
                        # Simple extraction
                        match = re.search(r'q=([^&]+)', query_str)
                        if match:
                            top_id = match.group(1) # This is the raw encoded string
                            top_name = unquote(top_id)
                            
                            # Insert into DB
                            # INSERT OR IGNORE to keep the earliest created_at
                            cur.execute("""
                                INSERT OR IGNORE INTO top_topics (top_id, top_name, created_at)
                                VALUES (?, ?, ?)
                            """, (top_id, top_name, created_at_str))
                            
                            if cur.rowcount > 0:
                                count_new += 1
                                # print(f"  Added: {top_name} ({created_at_str})")
                            else:
                                count_skipped += 1
                except Exception as e:
                    print(f"  Error parsing URL {url}: {e}")
                    
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            
    conn.commit()
    conn.close()
    print(f"\nProcessing complete.")
    print(f"New topics added: {count_new}")
    print(f"Topics skipped (already existed): {count_skipped}")

if __name__ == "__main__":
    process_files()
