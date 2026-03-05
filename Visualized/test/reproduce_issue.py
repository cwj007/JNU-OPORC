import sqlite3
import os
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(BASE_DIR))

from Visualized.api.alerts import generate_auto_alerts
from Visualized.api.database import query_db

db_path = r'e:\JNU-OPORC\Visualized\cache\hotsearch.db'

async def test_reproduction():
    print("--- Current '单贴高危负面预警' alerts ---")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, reference_id, title, user_id, alerts_time FROM alerts WHERE type = '单贴高危负面预警' ORDER BY id DESC LIMIT 5")
    rows = cur.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, RefID: {row[1]}, Title: {row[2]}, UserID: {row[3]}, CreatedAt: {row[4]}")
    
    initial_count = len(rows)
    
    print("\n--- Running generate_auto_alerts() ---")
    await generate_auto_alerts(force=True)
    
    print("\n--- After 1st run: '单贴高危负面预警' alerts ---")
    cur.execute("SELECT id, reference_id, title, user_id, alerts_time FROM alerts WHERE type = '单贴高危负面预警' ORDER BY id DESC LIMIT 5")
    rows = cur.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, RefID: {row[1]}, Title: {row[2]}, UserID: {row[3]}, CreatedAt: {row[4]}")
        
    print("\n--- Running generate_auto_alerts() again ---")
    await generate_auto_alerts(force=True)
    
    print("\n--- After 2nd run: '单贴高危负面预警' alerts ---")
    cur.execute("SELECT id, reference_id, title, user_id, alerts_time FROM alerts WHERE type = '单贴高危负面预警' ORDER BY id DESC LIMIT 5")
    rows = cur.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, RefID: {row[1]}, Title: {row[2]}, UserID: {row[3]}, CreatedAt: {row[4]}")
        
    conn.close()

if __name__ == "__main__":
    asyncio.run(test_reproduction())
