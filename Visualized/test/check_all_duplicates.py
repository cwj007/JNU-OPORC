import sqlite3
import os

db_path = r'e:\JNU-OPORC\Visualized\cache\hotsearch.db'

def check_all_burst_duplicates():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("--- Checking for ANY duplicate reference_ids in '单贴高危负面预警' ---")
    try:
        sql = """
            SELECT reference_id, COUNT(*) as count 
            FROM alerts 
            WHERE type = '单贴高危负面预警' 
            GROUP BY reference_id, user_id
            HAVING count > 1
        """
        cur.execute(sql)
        duplicates = cur.fetchall()
        
        if not duplicates:
            print("No duplicates found for (reference_id, user_id) pairs.")
        else:
            print(f"Found {len(duplicates)} pairs of (reference_id, user_id) with duplicate burst alerts.")
            for dup in duplicates:
                print(f"RefID: {dup['reference_id']}, UserID: {dup['user_id']}, Count: {dup['count']}")

        print("\n--- Checking for same reference_id across DIFFERENT user_ids for burst alerts ---")
        sql = """
            SELECT reference_id, COUNT(DISTINCT user_id) as user_count, GROUP_CONCAT(user_id) as users
            FROM alerts 
            WHERE type = '单贴高危负面预警' 
            GROUP BY reference_id
            HAVING user_count > 1
        """
        cur.execute(sql)
        cross_user_duplicates = cur.fetchall()
        if not cross_user_duplicates:
            print("No cross-user duplicates found for burst alerts.")
        else:
            print(f"Found {len(cross_user_duplicates)} RefIDs with alerts for multiple users.")
            for dup in cross_user_duplicates:
                print(f"RefID: {dup['reference_id']}, UserCount: {dup['user_count']}, Users: {dup['users']}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_all_burst_duplicates()
