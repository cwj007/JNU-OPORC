import sqlite3
import os
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(BASE_DIR))

from Visualized.api.alert_engine import NotificationService
from Visualized.api.database import execute_db, query_db

async def test_deduplication():
    # Setup test data
    ref_id = "TEST_REF_123"
    user_id = 999
    
    # Cleanup
    await execute_db("DELETE FROM alerts WHERE reference_id = ?", (ref_id,))
    
    print(f"--- Testing deduplication for RefID: {ref_id} ---")
    
    # 1. Send first alert (CRI)
    print("Sending 1st alert (CRI)...")
    await NotificationService.notify(
        "system", 
        "【综合风险预警-风险显著】Title 1", 
        "Content 1", 
        "medium", 
        reference_id=ref_id,
        user_id=user_id,
        rule_name="全网负面内容监测",
        rule_id=101
    )
    
    # 2. Send second alert (Burst) for same article
    print("\nSending 2nd alert (Burst) for same article...")
    await NotificationService.notify(
        "system", 
        "【单贴高危预警】Title 1", 
        "Content 2", 
        "high", 
        reference_id=ref_id,
        user_id=user_id,
        rule_name="单贴高危负面预警",
        rule_id=102
    )
    
    # 3. Check alerts table
    print("\n--- Checking alerts table ---")
    rows = await query_db("SELECT id, title, type FROM alerts WHERE reference_id = ? AND user_id = ?", (ref_id, user_id))
    for row in rows:
        print(f"ID: {row['id']}, Title: {row['title']}, Type: {row['type']}")
    
    if len(rows) == 1:
        print("\nSUCCESS: Deduplication worked! Only 1 alert for the same article.")
    else:
        print(f"\nFAILURE: Found {len(rows)} alerts. Deduplication failed.")

if __name__ == "__main__":
    asyncio.run(test_deduplication())
