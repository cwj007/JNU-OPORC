
import sys
from pathlib import Path
import traceback

BASE_DIR = Path(r"e:\JNU-OPORC")
sys.path.append(str(BASE_DIR))

try:
    from MediaCrawler.api.routers.crawler import router as mc_crawler_router
    with open("import_result.txt", "w") as f:
        f.write("Successfully imported MediaCrawler.api.routers.crawler")
except ImportError:
    with open("import_result.txt", "w") as f:
        traceback.print_exc(file=f)
        f.write("Import failed")
except Exception:
    with open("import_result.txt", "w") as f:
        traceback.print_exc(file=f)
        f.write("Import failed with exception")
