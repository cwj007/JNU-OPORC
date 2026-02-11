import sqlite3
import concurrent.futures
import requests
import urllib3
import re
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks
from .database import DB_PATH
from .config import PLATFORM_MAPPING, PLATFORM_NAMES

# 将 TrendRadar 项目根目录添加到 sys.path
TRENDRADAR_ROOT = Path(__file__).parent.parent.parent / "Trendradar"
if str(TRENDRADAR_ROOT) not in sys.path:
    sys.path.append(str(TRENDRADAR_ROOT))

try:
    from mcp_server.tools.data_query import DataQueryTools
    trendradar_tools = DataQueryTools(project_root=str(TRENDRADAR_ROOT))
except ImportError:
    print("Warning: TrendRadar MCP tools not found. Some functionality may be limited.")
    trendradar_tools = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 创建全局 Session 以复用连接，减少 SSL 握手失败
http_session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10, 
    pool_maxsize=10, 
    max_retries=requests.adapters.Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
)
http_session.mount("http://", adapter)
http_session.mount("https://", adapter)

router = APIRouter(prefix="/hotsearch", tags=["hotsearch"])


def sync_platform_data_from_trendradar(p_id, now_str):
    """从 TrendRadar 的 API/本地数据 同步数据"""
    if not trendradar_tools:
        return False
        
    try:
        # 映射平台 ID（Visualized ID -> TrendRadar ID）
        id_mapping = {
            "bilibili-hot-search": "bilibili",
        }
        tr_p_id = id_mapping.get(p_id, p_id)
        
        # 调用 TrendRadar 的最新数据接口
        result = trendradar_tools.get_latest_news(platforms=[tr_p_id], limit=50, include_url=True)
        
        if result.get("success") and result.get("news"):
            news_items = result["news"]
            # 使用统一的 save_to_db 处理趋势和批量插入
            save_to_db(p_id, news_items, now_str)
            print(f"Successfully synced {p_id} from TrendRadar API with trend")
            return True
            
        return False
    except Exception as e:
        print(f"Error syncing {p_id} from TrendRadar: {e}")
        return False

import time
import random

def sync_platform_data_live(p_id, now_str):
    """直接从 API 获取实时数据并存入 SQLite，带重试和多源兜底机制"""
    api_p_id = PLATFORM_MAPPING.get(p_id, p_id)
    
    # 优先使用的第一个 API (uapis.cn)
    source1_url = f"https://uapis.cn/api/v1/misc/hotboard?type={api_p_id}"
    # 兜底使用的第二个 API (newsnow)
    source2_url = f"https://newsnow.busiyi.world/api/s?id={api_p_id}&latest"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    }
    
    max_retries = 2
    retry_delay = 3
    
    # 尝试第一个 API (uapis.cn)
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                time.sleep(retry_delay + random.uniform(1, 3))
            
            print(f"Fetching from Source 1 (uapis) for {p_id} (Attempt {attempt + 1})")
            res = http_session.get(source1_url, headers=headers, timeout=15, verify=False)
            
            if res.status_code == 200:
                data = res.json()
                # 增加详细日志输出
                items = data.get("data") or data.get("list") or []
                print(f"DEBUG: [Source 1] Received {len(items)} items for {p_id}")
                if items:
                    print(f"DEBUG: [Source 1] First item: {items[0].get('title')}")
                
                if items:
                    # 统一格式
                    formatted_items = []
                    for item in items[:15]: # 只获取前 15 条
                        formatted_items.append({
                            "title": item.get("title", ""),
                            "url": item.get("url") or item.get("mobileUrl") or "#",
                            "hot": str(item.get("hot") or item.get("hot_value") or "0")
                        })
                    save_to_db(p_id, formatted_items, now_str)
                    print(f"Successfully synced {p_id} from Source 1 (uapis)")
                    return True
                else:
                    print(f"DEBUG: [Source 1] No items found in data for {p_id}. Full response: {data}")
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            print(f"Source 1 SSL/Connection error for {p_id} (Attempt {attempt + 1}): {e}")
        except Exception as e:
            print(f"Source 1 error for {p_id}: {e}")

    # 第一个 API 失败或没数据，尝试第二个 API (newsnow)
    print(f"Source 1 (uapis) failed for {p_id}, trying Source 2 (newsnow)...")
    try:
        res = http_session.get(source2_url, headers=headers, timeout=15, verify=False)
        if res.status_code == 200:
            data = res.json()
            # 增加详细日志输出
            items = data.get("items", [])
            print(f"DEBUG: [Source 2] Received {len(items)} items for {p_id}")
            if items:
                print(f"DEBUG: [Source 2] First item: {items[0].get('title')}")
                
            if data.get("status") in ["success", "cache"]:
                if items:
                    save_to_db(p_id, items, now_str)
                    print(f"Successfully synced {p_id} from Source 2 (newsnow)")
                    return True
                else:
                    print(f"DEBUG: [Source 2] Status is success but items list is empty for {p_id}")
            else:
                print(f"DEBUG: [Source 2] API returned non-success status: {data.get('status')} for {p_id}")
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
        print(f"Source 2 SSL/Connection error for {p_id}: {e}")
    except Exception as e:
        print(f"Source 2 error for {p_id}: {e}")
            
    return False

def save_to_db(p_id, items, now_str):
    """将获取到的条目统一存入数据库并计算趋势"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 1. 预先获取上一次抓取的所有记录，用于计算趋势
    cur.execute('SELECT DISTINCT fetch_time FROM hot_search_data WHERE platform = ? ORDER BY fetch_time DESC LIMIT 1', (p_id,))
    last_time_row = cur.fetchone()
    prev_ranks = {}
    if last_time_row:
        last_time = last_time_row[0]
        cur.execute('SELECT title, rank FROM hot_search_data WHERE platform = ? AND fetch_time = ?', (p_id, last_time))
        prev_ranks = {row[0]: row[1] for row in cur.fetchall()}

    # 2. 清理同平台同时间戳数据（防止重复插入）
    cur.execute('DELETE FROM hot_search_data WHERE platform = ? AND fetch_time = ?', (p_id, now_str))
    
    # 3. 准备批量插入数据
    insert_data = []
    for i, item in enumerate(items[:50]):
        title = item.get("title", "")
        item_url = item.get("url") or item.get("mobileUrl") or "#"
        hot = str(item.get("hot") or "0")
        rank = i + 1
        
        # 计算趋势
        prev_rank = prev_ranks.get(title)
        trend = 0
        if prev_rank:
            if prev_rank > rank:
                trend = 1
            elif prev_rank < rank:
                trend = -1
        
        insert_data.append((p_id, title, item_url, hot, rank, now_str, prev_rank, trend))
    
    # 4. 批量执行插入
    if insert_data:
        cur.executemany('''
            INSERT INTO hot_search_data (platform, title, url, hot_value, rank, fetch_time, previous_rank, trend)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', insert_data)
    
    conn.commit()
    conn.close()

def sync_platform_data(p_id, now_str):
    """同步平台数据的后台任务 (优先使用实时 API)"""
    
    # 添加一个随机的初始延迟，避免多个平台同时并发请求 API 导致被封禁或返回空
    time.sleep(random.uniform(0.5, 2.0))
    
    # 1. 优先尝试实时 API 获取 (不依赖文件，更及时)
    if sync_platform_data_live(p_id, now_str):
        return True
        
    # 2. 如果实时 API 失败，尝试 TrendRadar 的本地缓存 (DataQueryTools)
    if sync_platform_data_from_trendradar(p_id, now_str):
        return True
                
    return False

@router.get("/platforms")
async def get_hotsearch_platforms():
    """获取支持的热搜平台"""
    return PLATFORM_NAMES

@router.get("/all")
async def get_all_hotsearch_data(background_tasks: BackgroundTasks, refresh: bool = False):
    """获取所有平台的热搜数据。优先返回缓存，强制刷新时同步等待抓取结果。"""
    platforms = await get_hotsearch_platforms()
    
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    cache_threshold = (now_dt - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    
    # 如果是强制刷新，同步并行执行所有平台的抓取
    if refresh:
        print(f"Starting synchronous parallel refresh for all {len(platforms)} platforms...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(platforms), 10)) as executor:
            # 提交所有抓取任务
            future_to_platform = {executor.submit(sync_platform_data, p["id"], now_str): p["id"] for p in platforms}
            # 等待所有任务完成（设置 8 秒超时，防止某 API 极慢导致整体挂起）
            done, not_done = concurrent.futures.wait(future_to_platform.keys(), timeout=8)
            print(f"Parallel refresh completed: {len(done)} finished, {len(not_done)} timed out.")
    
    results = []
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    for p in platforms:
        p_id = p["id"]
        platform_result = {
            "id": p_id,
            "name": p["name"],
            "data": [],
            "status": "success",
            "error": None,
            "fetch_time": now_str
        }
        
        # 1. 查找最新缓存
        cur.execute('SELECT DISTINCT fetch_time FROM hot_search_data WHERE platform = ? ORDER BY fetch_time DESC LIMIT 1', (p_id,))
        last_time_row = cur.fetchone()
        
        if last_time_row:
            last_time = last_time_row[0]
            cur.execute('SELECT title, url, hot_value, rank, trend, previous_rank FROM hot_search_data WHERE platform = ? AND fetch_time = ? ORDER BY rank ASC', (p_id, last_time))
            platform_result["data"] = [
                {
                    "title": r[0], 
                    "url": r[1], 
                    "hot": r[2], 
                    "rank": r[3],
                    "trend": int(r[4]) if r[4] is not None and (str(r[4]).isdigit() or (isinstance(r[4], str) and r[4].startswith('-') and r[4][1:].isdigit())) else r[4],
                    "previous_rank": r[5]
                } for r in cur.fetchall()
            ]
            platform_result["fetch_time"] = last_time
            platform_result["status"] = "cached" if last_time > cache_threshold else "history"
            
            # 如果是正常请求且数据过期，则启动后台异步抓取
            if not refresh and last_time <= cache_threshold:
                background_tasks.add_task(sync_platform_data, p_id, now_str)
        else:
            # 完全没数据的情况
            if not refresh:
                # 异步启动抓取
                background_tasks.add_task(sync_platform_data, p_id, now_str)
                platform_result["status"] = "loading"
            else:
                # 强制刷新后还是没数据，可能是抓取失败
                platform_result["status"] = "error"
                platform_result["error"] = "抓取失败"

        results.append(platform_result)
        
    conn.close()
    return results

@router.get("/refresh/{platform_id}")
async def refresh_platform_data(platform_id: str, background_tasks: BackgroundTasks):
    """手动触发单个平台的数据更新并同步返回最新结果"""
    platforms = await get_hotsearch_platforms()
    p = next((x for x in platforms if x["id"] == platform_id), None)
    if not p:
        raise HTTPException(status_code=404, detail="Platform not found")
        
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # 同步执行抓取并等待 (设置超时)
    print(f"Refreshing single platform {platform_id} synchronously...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(sync_platform_data, platform_id, now_str)
        try:
            future.result(timeout=10) # 等待 10 秒
        except Exception as e:
            print(f"Sync for {platform_id} timed out or failed: {e}")
    
    # 返回最新抓取到的数据
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    platform_result = {
        "id": platform_id,
        "name": p["name"],
        "data": [],
        "status": "success",
        "error": None,
        "fetch_time": now_str
    }
    
    cur.execute('SELECT DISTINCT fetch_time FROM hot_search_data WHERE platform = ? ORDER BY fetch_time DESC LIMIT 1', (platform_id,))
    last_time_row = cur.fetchone()
    if last_time_row:
        last_time = last_time_row[0]
        cur.execute('SELECT title, url, hot_value, rank, trend, previous_rank FROM hot_search_data WHERE platform = ? AND fetch_time = ? ORDER BY rank ASC', (platform_id, last_time))
        platform_result["data"] = [
            {
                "title": r[0], 
                "url": r[1], 
                "hot": r[2], 
                "rank": r[3],
                "trend": int(r[4]) if r[4] is not None and (str(r[4]).isdigit() or (isinstance(r[4], str) and r[4].startswith('-') and r[4][1:].isdigit())) else r[4],
                "previous_rank": r[5]
            } for r in cur.fetchall()
        ]
        platform_result["fetch_time"] = last_time
        platform_result["status"] = "cached"
        
    conn.close()
    return platform_result

@router.get("/data/{platform_id}")
async def get_hotsearch_data(platform_id: str):
    """获取指定平台的热搜数据"""
    url = f"https://newsnow.busiyi.world/api/s?id={platform_id}&latest"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        if data.get("status") in ["success", "cache"]:
            return data
        else:
            raise HTTPException(status_code=500, detail=f"API Error: {data.get('status')}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
