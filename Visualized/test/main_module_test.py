import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000/api"

def test_auth():
    print("\n--- Testing Authentication ---")
    # 1. Login as root
    login_payload = {"username": "root", "password": "123456"}
    response = requests.post(f"{BASE_URL}/auth/login", json=login_payload)
    if response.status_code == 200:
        print("Root login successful")
        token = response.json()["token"]
    else:
        print(f"Root login failed: {response.status_code} - {response.text}")
        return None

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create a new user
    new_user_payload = {
        "username": f"testuser_{int(time.time())}",
        "password": "testpassword",
        "role": "user",
        "email": "test@example.com"
    }
    response = requests.post(f"{BASE_URL}/auth/users", json=new_user_payload, headers=headers)
    if response.status_code == 200:
        print(f"User '{new_user_payload['username']}' created successfully")
    else:
        print(f"User creation failed: {response.status_code} - {response.text}")

    # 3. Login as new user
    login_payload = {"username": new_user_payload["username"], "password": new_user_payload["password"]}
    response = requests.post(f"{BASE_URL}/auth/login", json=login_payload)
    if response.status_code == 200:
        print("New user login successful")
        user_token = response.json()["token"]
    else:
        print(f"New user login failed: {response.status_code} - {response.text}")
        return None

    # 4. Get profile
    user_headers = {"Authorization": f"Bearer {user_token}"}
    response = requests.get(f"{BASE_URL}/auth/me", headers=user_headers)
    if response.status_code == 200:
        print(f"Get profile successful: {response.json()['username']}")
    else:
        print(f"Get profile failed: {response.status_code} - {response.text}")

    return token

def test_crawler():
    print("\n--- Testing Crawler (Weibo & Zhihu) ---")
    # Start Weibo crawler (Search mode)
    payload = {
        "platform": "wb",
        "keywords": "AI",
        "crawler_type": "search",
        "save_option": "sqlite",
        "crawler_max_notes_count": 2
    }
    response = requests.post(f"{BASE_URL}/crawler/start", json=payload)
    if response.status_code == 200:
        print("Weibo crawler started")
    else:
        print(f"Weibo crawler start failed: {response.status_code} - {response.text}")

    # Check status
    time.sleep(2)
    response = requests.get(f"{BASE_URL}/crawler/status")
    print(f"Crawler status: {response.json().get('status')}")

    # Stop crawler
    response = requests.post(f"{BASE_URL}/crawler/stop")
    if response.status_code == 200:
        print("Crawler stopped")
    else:
        print(f"Crawler stop failed: {response.status_code} - {response.text}")

    # Start Zhihu crawler (Search mode)
    payload["platform"] = "zhihu"
    response = requests.post(f"{BASE_URL}/crawler/start", json=payload)
    if response.status_code == 200:
        print("Zhihu crawler started")
    else:
        print(f"Zhihu crawler start failed: {response.status_code} - {response.text}")

    time.sleep(2)
    requests.post(f"{BASE_URL}/crawler/stop")
    print("Zhihu crawler stopped")

def test_analysis_ops(admin_token):
    print("\n--- Testing Analysis Operations ---")
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Update analysis result
    # We need a valid note_id. Let's try to find one from the database first.
    # For testing purposes, we'll use a dummy note_id if we can't find one.
    note_id = "test_note_123"
    update_payload = {
        "note_id": note_id,
        "sentiment": "正面",
        "fine_grained_sentiment": "赞美",
        "intent": "分享",
        "irony_detected": False,
        "reasoning": "测试更新",
        "keywords": ["test", "api"],
        "original_data": {"note_id": note_id, "title": "Test Title"}
    }
    response = requests.post(f"{BASE_URL}/monitoring/update_training_result", json=update_payload, headers=headers)
    if response.status_code == 200:
        print("Update analysis result successful")
    else:
        print(f"Update analysis result failed: {response.status_code} - {response.text}")

    # 2. Update sentiment
    sentiment_payload = {
        "note_id": note_id,
        "comment_id": "0",
        "new_sentiment": "负面",
        "original_data": {"note_id": note_id}
    }
    response = requests.post(f"{BASE_URL}/monitoring/update_sentiment", json=sentiment_payload, headers=headers)
    if response.status_code == 200:
        print("Update sentiment successful")
    else:
        print(f"Update sentiment failed: {response.status_code} - {response.text}")

    # 3. Delete content
    response = requests.delete(f"{BASE_URL}/monitoring/content/{note_id}", headers=headers)
    if response.status_code == 200:
        print("Delete content successful")
    else:
        print(f"Delete content failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    admin_token = test_auth()
    if admin_token:
        test_crawler()
        test_analysis_ops(admin_token)
