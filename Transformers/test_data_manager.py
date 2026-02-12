
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from Transformers.processors.data_manager import DataManager
from Transformers.config import WEIBO_POSTS_FILE, WEIBO_COMMENTS_FILE
from Transformers import utils

def test_weibo_loading():
    utils.logger.info(f"[test_data_manager.test_weibo_loading] Testing Weibo data loading from:")
    utils.logger.info(f"[test_data_manager.test_weibo_loading] Posts: {WEIBO_POSTS_FILE}")
    utils.logger.info(f"[test_data_manager.test_weibo_loading] Comments: {WEIBO_COMMENTS_FILE}")
    
    dm = DataManager()
    # Mock download to avoid network errors
    dm._download_image = lambda url, path: True
    
    data = dm.load_weibo_data(str(WEIBO_POSTS_FILE), str(WEIBO_COMMENTS_FILE))
    
    if not data:
        utils.logger.error("[test_data_manager.test_weibo_loading] Error: No data loaded!")
        return

    utils.logger.info(f"\n[test_data_manager.test_weibo_loading] Loaded {len(data)} items.")
    
    # Check first few items
    for i, item in enumerate(data[:5]):
        utils.logger.info(f"[test_data_manager.test_weibo_loading] Item {i+1}:")
        utils.logger.info(f"[test_data_manager.test_weibo_loading] Type: {item['type']}")
        utils.logger.info(f"[test_data_manager.test_weibo_loading] Note ID: {item['note_id']}")
        utils.logger.info(f"[test_data_manager.test_weibo_loading] Top ID: {item['top_id']}")
        utils.logger.info(f"[test_data_manager.test_weibo_loading] Comment ID: {item['comment_id']}")
        utils.logger.info(f"[test_data_manager.test_weibo_loading] Content: {item['content'][:50]}...")
        
        # Verify context injection for comments
        if item['type'] == 'comment':
            if 'parent_content' in item:
                utils.logger.info(f"[test_data_manager.test_weibo_loading] Success: parent_content injected: {item['parent_content'][:30]}...")
            else:
                utils.logger.error("[test_data_manager.test_weibo_loading] Error: parent_content MISSING!")
            
            if 'parent_images' in item:
                utils.logger.info(f"[test_data_manager.test_weibo_loading] Success: parent_images injected: {len(item['parent_images'])} images")
            else:
                utils.logger.error("[test_data_manager.test_weibo_loading] Error: parent_images MISSING!")

if __name__ == "__main__":
    test_weibo_loading()
