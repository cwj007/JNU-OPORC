import sqlite3
import os

db_path = 'Visualized/cache/hotsearch.db'
if not os.path.exists(db_path):
    print("NOT FOUND")
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM alert_rules WHERE rule_type = "article_burst"')
    print(f"COUNT:{cur.fetchone()[0]}")
    conn.close()
