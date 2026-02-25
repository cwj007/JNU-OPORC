import sys
import os
import asyncio
from datetime import datetime

# Add project root to path
sys.path.append(r'E:\JNU-OPORC')

from Visualized.api.dashboard import (
    get_dashboard_stats,
    get_dashboard_trends,
    get_dashboard_map,
    get_dashboard_sentiment_fine,
    get_dashboard_intent,
    get_dashboard_wordcloud,
    get_dashboard_comments
)
from Visualized.api.alerts import get_alerts

async def test_dashboard_apis():
    print("Testing Dashboard APIs...")
    days = 7
    
    try:
        print("\n1. Testing get_dashboard_stats...")
        stats = await get_dashboard_stats(days)
        print(f"Stats Result: {stats}")
    except Exception as e:
        print(f"get_dashboard_stats FAILED: {e}")

    try:
        print("\n2. Testing get_dashboard_trends...")
        trends = await get_dashboard_trends(days)
        print(f"Trends Result (first 2): {trends[:2] if trends else 'Empty'}")
    except Exception as e:
        print(f"get_dashboard_trends FAILED: {e}")

    try:
        print("\n3. Testing get_dashboard_map...")
        map_data = await get_dashboard_map(days)
        print(f"Map Result (first 2): {map_data[:2] if map_data else 'Empty'}")
    except Exception as e:
        print(f"get_dashboard_map FAILED: {e}")

    try:
        print("\n4. Testing get_dashboard_sentiment_fine...")
        sentiment = await get_dashboard_sentiment_fine(days)
        print(f"Sentiment Result (first 2): {sentiment[:2] if sentiment else 'Empty'}")
    except Exception as e:
        print(f"get_dashboard_sentiment_fine FAILED: {e}")

    try:
        print("\n5. Testing get_dashboard_intent...")
        intent = await get_dashboard_intent(days)
        print(f"Intent Result (first 2): {intent[:2] if intent else 'Empty'}")
    except Exception as e:
        print(f"get_dashboard_intent FAILED: {e}")

    try:
        print("\n6. Testing get_dashboard_wordcloud...")
        wordcloud = await get_dashboard_wordcloud(days)
        print(f"Wordcloud Result (first 2): {wordcloud[:2] if wordcloud else 'Empty'}")
    except Exception as e:
        print(f"get_dashboard_wordcloud FAILED: {e}")

    try:
        print("\n7. Testing get_alerts...")
        # Pass None for current_user to simulate unauthenticated access
        alerts = await get_alerts(days=days, current_user=None)
        print(f"Alerts Result Keys: {alerts.keys()}")
    except Exception as e:
        print(f"get_alerts FAILED: {e}")
        import traceback
        traceback.print_exc()

    try:
        print("\n8. Testing get_dashboard_comments...")
        comments = await get_dashboard_comments(limit=5)
        print(f"Comments Result: {comments}")
        
        # Test with task_id
        print("\n9. Testing get_dashboard_comments with task_id...")
        comments_with_task = await get_dashboard_comments(limit=5, task_id=36) # Using task_id 36 for example
        print(f"Comments with Task Result: {comments_with_task}")
    except Exception as e:
        print(f"get_dashboard_comments FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_dashboard_apis())
