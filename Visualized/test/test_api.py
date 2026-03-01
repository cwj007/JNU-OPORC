import requests
import json

url = "http://localhost:8080/api/dashboard/stats?days=7"
try:
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"Error: {e}")

url_30 = "http://localhost:8080/api/dashboard/stats?days=30"
try:
    response = requests.get(url_30)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"Error: {e}")
