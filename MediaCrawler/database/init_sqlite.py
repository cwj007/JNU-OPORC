import asyncio
import os
import sys

# Add the project root to sys.path to ensure imports work correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_session import create_tables
from config import db_config

async def main():
    print(f"Initializing SQLite tables at: {db_config.SQLITE_DB_PATH}")
    try:
        await create_tables("sqlite")
        print("SQLite tables initialized successfully.")
    except Exception as e:
        print(f"Error initializing SQLite tables: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
