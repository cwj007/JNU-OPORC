import asyncio
from api.database import query_db

async def main():
    rows = await query_db("PRAGMA table_info(content);")
    print("Content table info:", rows)
    rows = await query_db("SELECT * FROM content LIMIT 1;")
    print("Content first row:", rows)
    rows = await query_db("PRAGMA table_info(comments);")
    print("Comments table info:", rows)
    rows = await query_db("SELECT * FROM comments LIMIT 1;")
    print("Comments first row:", rows)

if __name__ == "__main__":
    asyncio.run(main())
