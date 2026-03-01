
import requests
import json

BASE_URL = "http://localhost:8080/api/dashboard"

def test_endpoint(name, params):
    url = f"{BASE_URL}/{name}"
    try:
        r = requests.get(url, params=params)
        print(f"Testing {name}?{r.request.url.split('?')[-1]}")
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"  DEBUG: Type of data is {type(data)}")
            if isinstance(data, list):
                count = len(data)
                total_val = 0
                for item in data:
                    if isinstance(item, dict):
                        total_val += item.get('total', 0) or item.get('value', 0)
                    else:
                        total_val += item
                print(f"  Result: {count} items, Total value: {total_val}")
            elif isinstance(data, dict):
                print(f"  DEBUG: Dict keys are {list(data.keys())}")
                if 'comments' in data and isinstance(data['comments'], list):
                    print(f"  Result: {len(data['comments'])} comments")
                elif 'total' in data:
                    print(f"  Result: total={data['total']}, articles={data.get('articles')}, comments={data.get('comments')}")
                elif 'sentiment_distribution' in data:
                     print(f"  Result: {data}")
                else:
                    print(f"  Result: {data}")
        else:
            print(f"  Error: {r.text}")
    except Exception as e:
        import traceback
        print(f"  Exception: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    params = {"days": 30, "task_id": 29}
    endpoints = ["stats", "trends", "map", "sentiment_fine", "intent", "comments"]
    for ep in endpoints:
        test_endpoint(ep, params)
