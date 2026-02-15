import asyncio
import json
import sys
# Add project root to path
sys.path.append(r'E:\JNU-OPORC')

from Visualized.api.monitoring import get_monitoring_list

async def test_list():
    print("Testing get_monitoring_list with keyword='奥运'...")
    try:
        # Mocking database calls might be hard without a real DB context or mocking library
        # But we can try to run it against the real DB if available.
        
        # 1. Test with keyword to check relevance
        result = await get_monitoring_list(page=1, size=5, keyword="奥运", keyword_mode="full")
        items = result.get("items", [])
        print(f"Found {len(items)} items.")
        
        if items:
            first = items[0]
            print("\nFirst Item:")
            print(f"  Title: {first.get('title')}")
            print(f"  Content (Snippet): {first.get('content')[:50]}")
            print(f"  Source: {first.get('source')}")
            print(f"  Author: {first.get('author')}")
            print(f"  Sentiment: {first.get('sentiment')} ({first.get('sentiment_score')}%)")
            print(f"  Relevance: {first.get('relevance')}")
            
            # Check logic
            if "奥运" in (first.get("title") or ""):
                 print("  Title Match: Yes (+50)")
            else:
                 print("  Title Match: No")
                 
            count = (first.get("content") or "").count("奥运")
            print(f"  Content Match Count: {count} (+{min(count*10, 50)})")
            
            expected_score = 0
            if "奥运" in (first.get("title") or ""): expected_score += 50
            expected_score += min(count*10, 50)
            if expected_score > 100: expected_score = 100
            
            print(f"  Expected Score: {expected_score}")
            if first.get("relevance") == expected_score:
                print("  PASS: Relevance calculation correct.")
            else:
                print(f"  FAIL: Expected {expected_score}, got {first.get('relevance')}")
        
        # 2. Test without keyword to check sentiment aggregation
        print("\nTesting get_monitoring_list without keyword...")
        result_no_kw = await get_monitoring_list(page=1, size=50)
        items_no_kw = result_no_kw.get("items", [])
        
        found_zero_percent = False
        for item in items_no_kw:
            s = item.get('sentiment')
            score = item.get('sentiment_score')
            # Only print potential issues or a sample
            # print(f"ID: {item.get('note_id')} | Sentiment: {s} ({score}%)")
            
            if s != '中性' and score == 0:
                print(f"  FOUND THE ISSUE: ID: {item.get('note_id')} | Sentiment: {s} ({score}%)")
                found_zero_percent = True
                
        if not found_zero_percent:
            print(f"  No items found with Non-neutral sentiment and 0% score in first {len(items_no_kw)} items.")
            if items_no_kw:
                 print(f"  Sample first item: {items_no_kw[0].get('sentiment')} {items_no_kw[0].get('sentiment_score')}%")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_list())
