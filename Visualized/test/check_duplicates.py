import sqlite3
import os

db_path = r'e:\JNU-OPORC\Visualized\cache\hotsearch.db'

def check_duplicate_burst_alerts():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("--- Checking for duplicate '单贴高危负面预警' alerts ---")
    try:
        # Find reference_ids that have more than one '单贴高危负面预警'
        sql = """
            SELECT reference_id, COUNT(*) as count 
            FROM alerts 
            WHERE type = '单贴高危负面预警' 
            GROUP BY reference_id 
            HAVING count > 1
        """
        cur.execute(sql)
        duplicates = cur.fetchall()
        
        if not duplicates:
            print("No duplicate '单贴高危负面预警' alerts found by RefID.")
        else:
            print(f"Found {len(duplicates)} RefIDs with duplicate burst alerts.")
            for dup in duplicates[:10]:
                ref_id = dup['reference_id']
                count = dup['count']
                print(f"\nRefID: {ref_id}, Count: {count}")
                
                # Show details for these duplicates
                cur.execute("SELECT id, user_id, time, alerts_time FROM alerts WHERE reference_id = ? AND type = '单贴高危负面预警' ORDER BY id", (ref_id,))
                rows = cur.fetchall()
                for row in rows:
                    print(f"  ID: {row['id']}, UserID: {row['user_id']}, Time: {row['time']}, CreatedAt: {row['alerts_time']}")

        # Also check for rules of type 'article_burst'
        print("\n--- Checking 'article_burst' rules ---")
        cur.execute("SELECT id, name, user_id, is_active FROM alert_rules WHERE rule_type = 'article_burst'")
        rules = cur.fetchall()
        for rule in rules:
            print(f"Rule ID: {rule['id']}, Name: {rule['name']}, UserID: {rule['user_id']}, Active: {rule['is_active']}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_duplicate_burst_alerts()
