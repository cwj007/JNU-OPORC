
import sqlite3
import os
import json

db_path = r'e:\JNU-OPORC\Visualized\cache\hotsearch.db'

def check_rules():
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("--- Alert Rules ---")
    try:
        cur.execute("SELECT * FROM alert_rules")
        rows = cur.fetchall()
        print(f"Total rules: {len(rows)}")
        for row in rows:
            rd = dict(row)
            print(f"ID: {rd.get('id')}, Name: {rd.get('name')}, Type: {rd.get('rule_type')}, Active: {rd.get('is_active')}, User: {rd.get('user_id')}")
    except Exception as e:
        print(f"Error checking rules: {e}")

    print("\n--- Article Burst Rules specifically ---")
    try:
        cur.execute("SELECT COUNT(*) FROM alert_rules WHERE rule_type = 'article_burst'")
        count = cur.fetchone()[0]
        print(f"Article Burst rules count: {count}")
    except Exception as e:
        print(f"Error checking burst rules: {e}")

    print("\n--- Detailed check for RefID Qu5znkx87 ---")
    try:
        cur.execute("SELECT id, title, user_id, type, time FROM alerts WHERE reference_id = 'Qu5znkx87' ORDER BY id")
        rows = cur.fetchall()
        for row in rows:
            print(f"ID: {row['id']}, UserID: {row['user_id']}, Type: {row['type']}, Title: {row['title']}, Time: {row['time']}")
    except Exception as e:
        print(f"Error checking RefID: {e}")

    conn.close()

if __name__ == "__main__":
    check_rules()
