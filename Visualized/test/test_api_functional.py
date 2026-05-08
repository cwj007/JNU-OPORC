# 这是一个功能测试文件（用于测试 Visualized/app.py 中的 API 接口）
import requests
import time
import subprocess
import os
import sys

def test_config_platforms():
    # 假设 API 在本地 8080 端口运行
    url = "http://localhost:8080/config/platforms"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "platforms" in data and len(data["platforms"]) > 0:
                print("test_config_platforms: PASSED")
                return True
            else:
                print("test_config_platforms: FAILED (Unexpected data structure)")
        else:
            print(f"test_config_platforms: FAILED (Status code: {response.status_code})")
    except Exception as e:
        print(f"test_config_platforms: FAILED (Connection error: {e})")
    return False

if __name__ == "__main__":
    print("注意：此测试需要后端服务正在运行。")
    test_config_platforms()
