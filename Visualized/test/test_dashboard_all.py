
import http.client
import json

def test_api(path):
    conn = http.client.HTTPConnection("localhost", 8080)
    conn.request("GET", path)
    res = conn.getresponse()
    data = res.read()
    print(f"\nPath: {path}")
    print(f"Status: {res.status}")
    try:
        parsed = json.loads(data.decode('utf-8'))
        if isinstance(parsed, list):
             print(f"Result count: {len(parsed)}")
             non_zero = [item for item in parsed if (isinstance(item, dict) and item.get('total', 0) > 0) or (isinstance(item, dict) and 'value' in item and item['value'] > 0)]
             if non_zero:
                 print(f"Non-zero items: {len(non_zero)}")
                 print(f"Example: {non_zero[0]}")
             else:
                 if len(parsed) > 0: print(f"First item: {parsed[0]}")
        else:
             if 'comments' in parsed:
                 print(f"Comments count: {len(parsed['comments'])}")
                 if parsed['comments']: print(f"First comment: {parsed['comments'][0]['content'][:50]}...")
             else:
                 print(f"Result: {parsed}")
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        print(f"Raw data: {data[:100]}...")
    conn.close()

task_id = 29
days = 30

endpoints = [
    f"/api/dashboard/stats?days={days}&task_id={task_id}",
    f"/api/dashboard/trends?days={days}&task_id={task_id}",
    f"/api/dashboard/comments?task_id={task_id}",
    f"/api/dashboard/map?days={days}&task_id={task_id}",
    f"/api/dashboard/sentiment_fine?days={days}&task_id={task_id}",
    f"/api/dashboard/intent?days={days}&task_id={task_id}"
]

for ep in endpoints:
    test_api(ep)
