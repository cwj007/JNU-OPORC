
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(BASE_DIR))

from Visualized.api.database import init_db

if __name__ == "__main__":
    print("Running init_db()...")
    init_db()
    print("Done.")
