import sqlite3
import os

db_path = r'e:\JNU-OPORC\Visualized\cache\hotsearch.db'

def check_cross_type_duplicates():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("--- Checking for same article with multiple alert types ---")
    try:
        sql = """
            SELECT reference_id, COUNT(DISTINCT type) as type_count, GROUP_CONCAT(DISTINCT type) as types
            FROM alerts 
            GROUP BY reference_id, user_id
            HAVING type_count > 1
        """
        cur.execute(sql)
        duplicates = cur.fetchall()
        
        if not duplicates:
            print("No cross-type duplicates found.")
        else:
            print(f"Found {len(duplicates)} pairs of (reference_id, user_id) with multiple alert types.")
            # Show first 10
            for dup in duplicates[:10]:
                print(f"RefID: {dup['reference_id']}, Types: {dup['types']}, Count: {dup['type_count']}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_cross_type_duplicates()
