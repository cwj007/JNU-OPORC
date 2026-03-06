# -*- coding: utf-8 -*-
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

# 获取当前脚本所在目录 (tools)
_TOOLS_DIR = os.path.dirname(__file__)
# 获取 MediaCrawler 根目录 (tools 的上一级)
_ROOT_DIR = os.path.abspath(os.path.join(_TOOLS_DIR, ".."))
# 定义 browser_data 目录相对于根目录的路径
_BROWSER_DATA_DIR = os.path.join(_ROOT_DIR, "browser_data")
# 定义缓存文件相对于根目录的路径
CACHE_FILE = os.path.join(_BROWSER_DATA_DIR, "cookies_cache.json")

def _get_visualized_user_info(visualized_user_id: str) -> Optional[Dict[str, str]]:
    """
    从 Visualized 模块的数据库中查询用户信息。
    """
    try:
        # Visualized 目录与 MediaCrawler 目录同级
        visualized_db_path = os.path.join(os.path.dirname(_ROOT_DIR), "Visualized", "cache", "hotsearch.db")
        if not os.path.exists(visualized_db_path):
            return None

        # 使用 sqlite3 直接查询，避免循环依赖
        conn = sqlite3.connect(visualized_db_path)
        cur = conn.cursor()
        # 用户表的字段是 username
        cur.execute("SELECT id, username FROM users WHERE id = ?", (visualized_user_id,))
        row = cur.fetchone()
        conn.close()

        if row:
            return {
                "id": str(row[0]),
                "username": row[1]
            }
    except Exception:
        pass
    return None

def save_cookie_cache(platform: str, user_id: str, user_name: str, cookie_str: str, visualized_user_id: Optional[str] = None):
    """
    Save cookies to a local JSON file.
    """
    # 如果用户信息未知，且提供了可视化系统用户 ID，尝试从系统数据库补全用户信息
    if (user_id == "unknown" or user_name == "未知用户") and visualized_user_id:
        v_info = _get_visualized_user_info(str(visualized_user_id))
        if v_info:
            if user_id == "unknown":
                # 使用系统用户 ID
                user_id = v_info['id']
            if user_name == "未知用户":
                user_name = v_info['username']

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

    # 使用 visualized_user_id 作为 key 的一部分，防止不同用户在同一个平台上爬取同一个账号时发生冲突
    cache_key = f"{user_id}_{visualized_user_id}" if visualized_user_id else user_id
    
    cache[platform][cache_key] = {
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
    获取指定平台的所有缓存 Cookie，如果提供了 visualized_user_id，则进行严格过滤。
    """
    if not os.path.exists(CACHE_FILE):
        return []

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
            platform_cache = cache.get(platform, {})
            cookies = list(platform_cache.values())
            
            # 严格过滤逻辑
            if visualized_user_id:
                # 只返回属于该用户的 Cookie。不再返回 visualized_user_id 为 None 的，
                # 除非 visualized_user_id 本身就是 'None' 字符串（根据前端可能的传递方式）
                # 我们统一转换为字符串进行比较，处理 None 值的各种情况
                v_id_str = str(visualized_user_id)
                cookies = [c for c in cookies if str(c.get("visualized_user_id")) == v_id_str]
            else:
                # 如果没有提供 visualized_user_id，则只返回没有归属的 Cookie (未知用户)
                # 这样可以防止未登录用户看到已登录用户的 Cookie
                cookies = [c for c in cookies if c.get("visualized_user_id") is None]
                
            # 按更新时间排序，最新的在前
            cookies.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return cookies
    except Exception:
        return []

def get_all_cookie_cache(visualized_user_id: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    获取所有平台的所有缓存 Cookie，如果提供了 visualized_user_id，则进行严格过滤。
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
                    v_id_str = str(visualized_user_id)
                    cookies = [c for c in cookies if str(c.get("visualized_user_id")) == v_id_str]
                else:
                    cookies = [c for c in cookies if c.get("visualized_user_id") is None]
                
                # 按更新时间排序
                cookies.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
                result[platform] = cookies
            return result
    except Exception:
        return {}

def get_latest_cookie_str(platform: str, visualized_user_id: Optional[str] = None) -> str:
    """
    获取指定平台和用户的最新 Cookie 字符串，用于前端 textarea 填充。
    """
    cookies = get_cookie_cache(platform, visualized_user_id)
    if cookies:
        return cookies[0].get("cookie_str", "")
    return ""
