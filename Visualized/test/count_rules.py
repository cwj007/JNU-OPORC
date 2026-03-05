import sqlite3
db_path = 'Visualized/cache/hotsearch.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM alert_rules WHERE rule_type = "article_burst"')
print(f"Article Burst rules count: {cur.fetchone()[0]}")
cur.execute('SELECT COUNT(*) FROM alert_rules')
print(f"Total alert rules count: {cur.fetchone()[0]}")
conn.close()
