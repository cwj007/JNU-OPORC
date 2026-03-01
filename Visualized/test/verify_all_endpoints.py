import asyncio
import json
from Visualized.api.dashboard import get_dashboard_stats, get_dashboard_trends, get_dashboard_map, get_dashboard_sentiment_fine, get_dashboard_intent, get_dashboard_wordcloud
from Visualized.api.database import init_db

async def test_endpoint(name, func, **kwargs):
    print(f"\n--- Testing {name} ---")
    try:
        res = await func(**kwargs)
        if res.get("status") == "success":
            print(f"Status: SUCCESS")
            if name == "stats":
                print(f"Articles: {res.get('articles')}")
                print(f"Comments: {res.get('comments')}")
                print(f"Total: {res.get('total')}")
            elif name == "trends":
                print(f"Labels count: {len(res.get('labels', []))}")
                print(f"Articles sum: {sum(res.get('articles', []))}")
            elif name == "map":
                print(f"Data points: {len(res.get('data', []))}")
            elif name == "sentiment_fine":
                print(f"Data points: {len(res.get('data', []))}")
                print(f"Data: {res.get('data')}")
            elif name == "intent":
                print(f"Data points: {len(res.get('data', []))}")
                print(f"Data: {res.get('data')}")
            elif name == "wordcloud":
                print(f"Keywords count: {len(res.get('data', []))}")
        else:
            print(f"Status: {res.get('status')}")
            print(f"Error: {res.get('error') or res.get('message')}")
    except Exception as e:
        print(f"Exception in {name}: {e}")

async def main():
    task_id = 36
    days = 30
    
    await test_endpoint("stats", get_dashboard_stats, days=days, task_id=task_id)
    await test_endpoint("trends", get_dashboard_trends, days=days, task_id=task_id)
    await test_endpoint("map", get_dashboard_map, days=days, task_id=task_id)
    await test_endpoint("sentiment_fine", get_dashboard_sentiment_fine, days=days, task_id=task_id)
    await test_endpoint("intent", get_dashboard_intent, days=days, task_id=task_id)
    # wordcloud might be slow or fail if jieba not installed, but let's try
    await test_endpoint("wordcloud", get_dashboard_wordcloud, days=days, task_id=task_id)

if __name__ == "__main__":
    asyncio.run(main())
