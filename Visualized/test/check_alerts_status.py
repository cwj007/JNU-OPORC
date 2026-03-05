import sqlite3
import json
import os
from datetime import datetime

db_path = 'Visualized/cache/hotsearch.db'
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("--- Alert Rules (ALL) ---")
cur.execute("SELECT * FROM alert_rules")
rows = cur.fetchall()
print(f"Total rules: {len(rows)}")
for row in rows:
    # Convert Row to dict to see all columns
    rd = dict(row)
    print(f"ID: {rd['id']}, Name: {rd['name']}, Type: {rd['rule_type']}, Active: {rd['is_active']}, User: {rd['user_id']}, Window: {rd['time_window']}")

print("\n--- Alert Rules (User NULL Only) ---")
cur.execute("SELECT id, name, rule_type, is_active, user_id FROM alert_rules WHERE user_id IS NULL")
for row in cur.fetchall():
    print(f"ID: {row['id']}, Name: {row['name']}, Type: {row['rule_type']}, Active: {row['is_active']}, User: {row['user_id']}")

print("\n--- Alert Rules (Active Only) ---")
cur.execute("SELECT id, name, rule_type, is_active, user_id FROM alert_rules WHERE is_active = 1")
for row in cur.fetchall():
    print(f"ID: {row['id']}, Name: {row['name']}, Type: {row['rule_type']}, Active: {row['is_active']}, User: {row['user_id']}")

print("\n--- Recent '单贴高危预警' Alerts (Today or Latest 10) ---")
today = datetime.now().strftime('%Y-%m-%d')
cur.execute("SELECT id, title, reference_id, user_id, time, alerts_time FROM alerts WHERE title LIKE '%单贴高危预警%' ORDER BY id DESC LIMIT 10")
for row in cur.fetchall():
    print(f"ID: {row['id']}, Title: {row['title']}, RefID: {row['reference_id']}, UserID: {row['user_id']}, Time: {row['time']}, AlertsTime: {row['alerts_time']}")

print("\n--- Check for duplicate alerts for same RefID (ANY title) ---")
cur.execute("""
    SELECT reference_id, COUNT(*) as cnt, GROUP_CONCAT(id) as ids, GROUP_CONCAT(alerts_time) as times, GROUP_CONCAT(title) as titles
    FROM alerts 
    WHERE reference_id IS NOT NULL AND reference_id != ''
    GROUP BY reference_id 
    HAVING cnt > 1 
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"RefID: {row['reference_id']}, Count: {row['cnt']}")
    print(f"  IDs: {row['ids']}")
    print(f"  Times: {row['times']}")
    print(f"  Titles: {row['titles']}")

print("\n--- Check for alerts with UserID vs NULL ---")
cur.execute("SELECT user_id, COUNT(*) FROM alerts GROUP BY user_id")
for row in cur.fetchall():
    print(f"UserID: {row[0]}, Count: {row[1]}")

conn.close()
