
import sys
import os
import asyncio
from pathlib import Path

# Add project root and MediaCrawler to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEDIA_CRAWLER_DIR = PROJECT_ROOT / "MediaCrawler"
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(MEDIA_CRAWLER_DIR))

# Now try to import
try:
    from MediaCrawler.media_platform.weibo.get_specified_ids import WeiboTopIDExtractor
    print("Import successful")
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

async def test_run():
    print("Initializing extractor...")
    extractor = WeiboTopIDExtractor()
    # We don't want to actually run the full extraction if it takes too long or requires interaction
    # But the user wants it to run automatically.
    # The script has interactive input: 
    # "choice = await self.async_input(">> ", timeout=5.0)"
    # I need to check if I can bypass this interaction.
    
    # Let's inspect the code of get_specified_ids.py again to see how to bypass input.
    pass

if __name__ == "__main__":
    asyncio.run(test_run())
