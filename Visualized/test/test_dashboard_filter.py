import http.client
import json

def test_api(path):
    conn = http.client.HTTPConnection("localhost", 8080)
    conn.request("GET", path)
    res = conn.getresponse()
    data = res.read()
    print(f"Path: {path}")
    print(f"Status: {res.status}")
    try:
        parsed = json.loads(data.decode('utf-8'))
        # Only print summary if it's too large
        if isinstance(parsed, list):
             print(f"Result count: {len(parsed)}")
             non_zero = [item for item in parsed if item.get('total', 0) > 0]
             print(f"Non-zero items: {len(non_zero)}")
             for item in non_zero:
                 print(item)
             if len(parsed) > 0 and not non_zero:
                 print(f"First item (all zero): {parsed[0]}")
        else:
             print(f"Result: {parsed}")
    except:
        print(f"Raw data: {data[:100]}...")
    conn.close()

print("Testing without task_id:")
test_api("/api/dashboard/stats?days=30")

print("\nTesting with task_id=29:")
test_api("/api/dashboard/stats?days=30&task_id=29")

print("\nTesting trends with task_id=29:")
test_api("/api/dashboard/trends?days=30&task_id=29")
