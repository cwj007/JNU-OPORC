
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from Transformers.processors.data_manager import DataManager
from Transformers.config import WEIBO_POSTS_FILE, WEIBO_COMMENTS_FILE

def test_weibo_loading():
    print(f"Testing Weibo data loading from:")
    print(f"Posts: {WEIBO_POSTS_FILE}")
    print(f"Comments: {WEIBO_COMMENTS_FILE}")
    
    dm = DataManager()
    data = dm.load_weibo_data(str(WEIBO_POSTS_FILE), str(WEIBO_COMMENTS_FILE))
    
    if not data:
        print("Error: No data loaded!")
        return

    print(f"\nLoaded {len(data)} items.")
    
    # Check first few items
    for i, item in enumerate(data[:5]):
        print(f"\nItem {i+1}:")
        print(f"  Type: {item['type']}")
        print(f"  Note ID: {item['note_id']}")
        print(f"  Top ID: {item['top_id']}")
        print(f"  Comment ID: {item['comment_id']}")
        print(f"  Content: {item['content'][:50]}...")
        
        # Verify top_id and note_id logic
        if item['top_id'] == item['note_id']:
            print("  [Warning] top_id is equal to note_id (Normal if the CSV data has them identical)")
        else:
            print("  [Success] top_id and note_id are DIFFERENT")

if __name__ == "__main__":
    test_weibo_loading()
