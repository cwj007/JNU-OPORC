import asyncio
import sys
# Add project root to path
sys.path.append(r'E:\JNU-OPORC')

from Visualized.api.monitoring import get_monitoring_list

async def test_sorting():
    print("Testing get_monitoring_list sorting...")
    
    try:
        # 1. Test descending (default)
        print("\n--- Testing DESC Sorting ---")
        result_desc = await get_monitoring_list(page=1, size=3, sort_by="time_desc")
        items_desc = result_desc.get("items", [])
        
        last_time = None
        for item in items_desc:
            curr_time = item.get("created_at")
            print(f"Time: {curr_time}")
            if last_time:
                if curr_time <= last_time:
                    pass # Correct
                else:
                    print("  FAIL: Time is not descending!")
            last_time = curr_time
            
        # 2. Test ascending
        print("\n--- Testing ASC Sorting ---")
        result_asc = await get_monitoring_list(page=1, size=3, sort_by="time_asc")
        items_asc = result_asc.get("items", [])
        
        last_time = None
        for item in items_asc:
            curr_time = item.get("created_at")
            print(f"Time: {curr_time}")
            if last_time:
                if curr_time >= last_time:
                    pass # Correct
                else:
                    print("  FAIL: Time is not ascending!")
            last_time = curr_time
            
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_sorting())
