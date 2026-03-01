
import asyncio
from Visualized.api.dashboard import get_dashboard_stats
from Visualized.api.database import init_db

async def main():
    try:
        # init_db() # Ensure DB is initialized
        res = await get_dashboard_stats(days=30, task_id=36)
        print("\nResult:")
        for k, v in res.items():
            print(f"{k}: {v}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
