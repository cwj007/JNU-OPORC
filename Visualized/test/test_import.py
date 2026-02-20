
import sys
from pathlib import Path
import traceback

BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))

try:
    from MediaCrawler.api.routers.crawler import router as mc_crawler_router
    print("Successfully imported MediaCrawler.api.routers.crawler")
except ImportError:
    traceback.print_exc()
    print("Import failed")
except Exception:
    traceback.print_exc()
    print("Import failed with exception")
