import requests
import json

def test_api():
    url = "http://127.0.0.1:8080/"
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        print(f"Response Length: {len(response.text)}")
        print(f"Response Preview: {response.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()
