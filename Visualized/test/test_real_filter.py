
import sys
import os

# Add project root to sys.path to import from Visualized.api
sys.path.append(os.path.abspath('.'))

from Visualized.api.dashboard import build_task_filter

def test_filter():
    task_id = 36
    sql, params = build_task_filter(task_id, mode="full")
    print(f"Task ID: {task_id}")
    print(f"SQL: {sql}")
    print(f"Params: {params}")

if __name__ == "__main__":
    test_filter()
