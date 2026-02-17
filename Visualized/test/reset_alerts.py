import sys
import os
from pathlib import Path
import json

# Set up path to allow imports from api module
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir))

from api.database import execute_db
from api.alert_engine import AlertEngine

def main():
    print("1. Clearing existing alerts...")
    try:
        # Delete all alerts
        execute_db("DELETE FROM alerts")
        # Reset auto-increment counter
        execute_db("DELETE FROM sqlite_sequence WHERE name='alerts'")
        print("   - Alerts table cleared.")
    except Exception as e:
        print(f"   - Error clearing alerts: {e}")

    print("2. Re-detecting from historical data (past 7 days)...")
    try:
        engine = AlertEngine()
        engine.load_rules()
        if not engine.rules:
             print("   - No active alert rules found. Please create rules first.")
        else:
             print(f"   - Found {len(engine.rules)} active rules.")
             # Check last 7 days (or 3 days as user mentioned in previous chats, let's go with 7 for broader coverage)
             engine.run_check(override_days=7)
             print("   - Detection complete.")
    except Exception as e:
        print(f"   - Error during detection: {e}")

if __name__ == "__main__":
    main()
