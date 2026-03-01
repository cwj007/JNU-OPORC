
import sys
import os
import requests

def test_comments_task29():
    url = "http://localhost:8080/api/dashboard/comments?limit=50&task_id=29"
    try:
        r = requests.get(url)
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Result count: {len(data.get('comments', []))}")
        if data.get('comments'):
            for c in data['comments'][:10]:
                print(f"[{c['platform']}] {c['author']}: {c['content'][:100]}...")
        else:
            print(f"Full response: {data}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_comments_task29()
