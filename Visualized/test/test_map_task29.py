
import requests
import json

url = "http://localhost:8080/api/dashboard/map?days=30&task_id=29"
r = requests.get(url)
print(f"Status: {r.status_code}")
data = r.json()
print(f"Count: {len(data)}")
for item in data[:5]:
    print(item)
print(f"Total value: {sum(item.get('value', 0) for item in data)}")
