import sys
import os
import asyncio
import json

# Add project root to path
sys.path.append(r'E:\JNU-OPORC')

from Visualized.api.monitoring import get_item_detail

async def test_detail():
    note_id = "QpY3ppQCB" # From previous check
    comment_id = "0"
    
    print(f"Testing get_item_detail with note_id={note_id}, comment_id={comment_id}")
    try:
        result = await get_item_detail(note_id, comment_id)
        
        print("\nResult Keys:", result.keys())
        print("\nArticle Content Preview:", result.get("content", "")[:50])
        
        comments = result.get("comments", [])
        print(f"\nComments Count: {len(comments)}")
        
        if comments:
            print("First Comment:", comments[0])
            
        print("\nSentiment Analysis:", result.get("sentiment_analysis"))
        
        # Verify required fields for frontend
        required_fields = ["content", "comments", "sentiment_analysis", "trained_keywords"]
        missing = [f for f in required_fields if f not in result]
        if missing:
            print(f"\nFAIL: Missing fields: {missing}")
        else:
            print("\nSUCCESS: All required fields present.")
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_detail())
