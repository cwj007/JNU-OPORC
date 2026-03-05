import sqlite3
db_path = r"e:\JNU-OPORC\Transformers\cache\processed_ids.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check content on March 4
cursor.execute("SELECT count(*) FROM content WHERE created_at LIKE '2026-03-04%'")
c4 = cursor.fetchone()[0]
print(f"Content on March 4: {c4}")

# Check comments on March 4
cursor.execute("SELECT count(*) FROM comments WHERE created_at LIKE '2026-03-04%'")
cm4 = cursor.fetchone()[0]
print(f"Comments on March 4: {cm4}")

# Total
print(f"Total on March 4: {c4 + cm4}")

conn.close()
