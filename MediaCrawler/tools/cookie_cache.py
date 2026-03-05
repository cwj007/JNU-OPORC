# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

# 获取当前脚本所在目录 (tools)
_TOOLS_DIR = os.path.dirname(__file__)
# 获取 MediaCrawler 根目录 (tools 的上一级)
_ROOT_DIR = os.path.join(_TOOLS_DIR, "..")
# 定义 browser_data 目录相对于根目录的路径
_BROWSER_DATA_DIR = os.path.join(_ROOT_DIR, "browser_data")
# 定义缓存文件相对于根目录的路径
CACHE_FILE = os.path.join(_BROWSER_DATA_DIR, "cookies_cache.json")

def save_cookie_cache(platform: str, user_id: str, user_name: str, cookie_str: str, visualized_user_id: Optional[str] = None):
    """
    Save cookies to a local JSON file.
    """
    if not os.path.exists(_BROWSER_DATA_DIR):
        os.makedirs(_BROWSER_DATA_DIR)

    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    if platform not in cache:
        cache[platform] = {}

    cache[platform][user_id] = {
        "user_id": user_id,
        "user_name": user_name,
        "cookie_str": cookie_str,
        "visualized_user_id": visualized_user_id,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=4)

def get_cookie_cache(platform: str, visualized_user_id: Optional[str] = None) -> List[Dict]:
    """
    Get all cached cookies for a platform, optionally filtered by visualized_user_id.
    """
    if not os.path.exists(CACHE_FILE):
        return []

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
            platform_cache = cache.get(platform, {})
            cookies = list(platform_cache.values())
            if visualized_user_id:
                # 过滤出属于该用户，或者没有 visualized_user_id 的 Cookie (为了兼容以前的数据)
                cookies = [c for c in cookies if c.get("visualized_user_id") == visualized_user_id or c.get("visualized_user_id") is None]
            return cookies
    except Exception:
        return []

def get_all_cookie_cache(visualized_user_id: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    Get all cached cookies for all platforms, optionally filtered by visualized_user_id.
    """
    if not os.path.exists(CACHE_FILE):
        return {}

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
            result = {}
            for platform, users in cache.items():
                cookies = list(users.values())
                if visualized_user_id:
                    cookies = [c for c in cookies if c.get("visualized_user_id") == visualized_user_id or c.get("visualized_user_id") is None]
                result[platform] = cookies
            return result
    except Exception:
        return {}
