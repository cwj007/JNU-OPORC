
import sys
import os
import requests

def test_trends_30():
    url = "http://localhost:8080/api/dashboard/trends?days=30&task_id=29"
    try:
        r = requests.get(url)
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Result count: {len(data)}")
        found = False
        for item in data:
            if item['total'] > 0:
                print(f"Found data on {item['date']}: {item}")
                found = True
        if not found:
            print("No data found in any item")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_trends_30()
