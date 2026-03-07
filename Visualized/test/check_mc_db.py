import sqlite3
from pathlib import Path

MC_DB_PATH = Path(r"e:\JNU-OPORC\MediaCrawler\database\sqlite_tables.db")

def check_mc_db():
    if not MC_DB_PATH.exists():
        print(f"Error: Database file not found at {MC_DB_PATH}")
        return

    conn = sqlite3.connect(MC_DB_PATH)
    cur = conn.cursor()
    
    print(f"Inspecting database {MC_DB_PATH}")
    
    # 获取所有表名
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    print(f"Tables found: {[t[0] for t in tables]}")
    
    for table_name in [t[0] for t in tables]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            print(f"Table '{table_name}': {count} records")
            
            # 检查是否有 last_modify_ts 或 similar time columns
            cur.execute(f"PRAGMA table_info({table_name})")
            columns = [c[1] for c in cur.fetchall()]
            time_cols = [c for c in columns if 'time' in c.lower() or 'date' in c.lower() or 'ts' in c.lower()]
            if time_cols:
                # 检查最新时间
                col = time_cols[0]
                cur.execute(f"SELECT {col} FROM {table_name} ORDER BY {col} DESC LIMIT 1")
                latest = cur.fetchone()
                if latest:
                    print(f"  - Latest {col}: {latest[0]}")
        except Exception as e:
            print(f"Error checking table {table_name}: {e}")

    conn.close()

if __name__ == "__main__":
    check_mc_db()
