import sqlite3
import concurrent.futures
import requests
import json
import urllib3
import re
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from .database import DB_PATH, CACHE_DIR, query_db, execute_db
from .auth import get_current_user, User
from .config import SOURCE1_PLATFORMS, SOURCE2_PLATFORMS, PLATFORM_NAMES, ALL_PLATFORMS, HOTSEARCH_SOURCES

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
        }
        tr_p_id = id_mapping.get(p_id, p_id)
        
        # 调用 TrendRadar 的最新数据接口
        result = trendradar_tools.get_latest_news(platforms=[tr_p_id], limit=100, include_url=True)
        
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
import asyncio

async def start_periodic_sync():
    """启动周期性数据同步任务"""
    while True:
        try:
            print(f"[{datetime.now()}] Starting scheduled background sync for all platforms...")
            sync_all_platforms()
            print(f"[{datetime.now()}] Scheduled background sync completed.")
        except Exception as e:
            print(f"Error in background sync: {e}")
        
        # 每 30 分钟同步一次
        await asyncio.sleep(30 * 60)

def sync_all_platforms():
    """同步所有平台的数据 (两个 API 源的所有平台)"""
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # 使用 ALL_PLATFORMS 确保同步两个 API 的所有平台
    platforms = ALL_PLATFORMS
    
    print(f"Syncing {len(platforms)} platforms in background...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(platforms), 10)) as executor:
        # 使用 list() 强制迭代完成
        list(executor.map(lambda p: sync_platform_data(p["id"], now_str, skip_sleep=True), platforms))

def clean_title(t):
    if not t: return ""
    # 去除标题中的 # 标签、空格、换行符、以及常见的括弧内容
    t = str(t).lower().strip()
    # 移除开头的 [数字] 或 数字. (如 1. 标题)
    t = re.sub(r'^\d+[.\s、]+', '', t)
    # 针对今日头条等平台，移除标题中可能存在的序号 (如 "1 正部级..." -> "正部级...")
    # 匹配开头是数字后跟空格的情况
    t = re.sub(r'^\d+\s+', '', t)
    # 移除常见的后缀/前缀标签
    t = re.sub(r'\[.*?\]|【.*?】|\(.*?\)|（.*?）', '', t)
    # 针对一些平台可能带有的热度后缀，如 " (热)" 或 " (新)"
    t = re.sub(r'\s*\(\s*热\s*\)|\s*\(\s*新\s*\)|\s*\(\s*沸\s*\)|\s*\(\s*荐\s*\)', '', t)
    t = re.sub(r'\s*热$|\s*新$|\s*沸$|\s*荐$', '', t)
    # 移除特殊符号和标点
    t = re.sub(r'[#!\?！？，。：；“”‘’"\'\(\)（）\-\+_=\[\]\{\}、\s]', '', t)
    return t

def get_last_titles(p_id):
    """获取该平台最近一次抓取的清洗后的标题列表，用于判断 API 数据是否刷新"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cur = conn.cursor()
        cur.execute('SELECT fetch_time FROM hot_search_data WHERE platform = ? ORDER BY fetch_time DESC LIMIT 1', (p_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return []
        
        last_time = row[0]
        cur.execute('SELECT title FROM hot_search_data WHERE platform = ? AND fetch_time = ? ORDER BY rank ASC', (p_id, last_time))
        titles = [clean_title(r[0]) for r in cur.fetchall()]
        conn.close()
        return titles
    except Exception as e:
        print(f"Error getting last titles for {p_id}: {e}")
        return []

def sync_platform_data_live(p_id, now_str, preferred_source=None):
    """直接从 API 获取实时数据并存入 SQLite，带重试和多源兜底机制"""
    # 分别获取两个源对应的平台 ID
    s1_api_p_id = SOURCE1_PLATFORMS.get(p_id, p_id)
    s2_api_p_id = SOURCE2_PLATFORMS.get(p_id, p_id)
    
    # 获取上一次抓取的内容，用于去重/判断刷新
    last_cleaned_titles = get_last_titles(p_id)
    
    # 优先使用的第一个 API (uapis.cn) - 用户首选
    source1_url = HOTSEARCH_SOURCES["source1"].format(platform=s1_api_p_id, timestamp=int(time.time()))
    # 兜底使用的第二个 API (newsnow)
    source2_url = HOTSEARCH_SOURCES["source2"].format(platform=s2_api_p_id, timestamp=int(time.time()))
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    }
    
    # 确定抓取顺序
    sources_to_try = []
    if preferred_source == "2":
        sources_to_try = [
            ("source2", source2_url, s2_api_p_id),
            ("source1", source1_url, s1_api_p_id)
        ]
    else:
        sources_to_try = [
            ("source1", source1_url, s1_api_p_id),
            ("source2", source2_url, s2_api_p_id)
        ]

    for source_name, url, api_p_id in sources_to_try:
        try:
            print(f"Fetching from {source_name} for {p_id}")
            res = http_session.get(url, headers=headers, timeout=15, verify=False)
            if res.status_code == 200:
                data = res.json()
                items = []
                if source_name == "source1":
                    items_raw = data.get("data") or data.get("list") or []
                    for item in items_raw[:100]:
                        # 尝试从多个字段获取热度值
                        hot_val = item.get("hot") or item.get("hot_value") or item.get("hotValue") or item.get("heat") or item.get("index") or ""
                        
                        # 针对知乎 (zhihu) 平台，Source 1 API 有时返回的热度值确实很小 (如 774)，
                        # 这可能是 API 本身的数据源问题（例如取成了热度排名的原始分值而非展示热度）。
                        # 在存入数据库之前，我们需要在这里做一次处理。
                        # 但为了稳妥，我们在 save_to_db 中统一处理，因为那里可以拿到最终的 p_id。
                        
                        items.append({
                            "title": item.get("title", ""),
                            "url": item.get("url") or item.get("mobileUrl") or "#",
                            "hot": str(hot_val)
                        })
                        if items[-1]["hot"] == "0" or not items[-1]["hot"]:
                            items[-1]["hot"] = None
                else: # source2
                    items = data.get("items") or []
                
                if items and len(items) >= 5:
                    # 不再进行标题去重校验，因为 30 分钟缓存已经保证了抓取频率，
                    # 每次抓取都保存可以确保热度值（hot）等实时数据得到更新。
                    print(f"{source_name} for {p_id} fetched successfully. Saving.")
                    save_to_db(p_id, items, now_str)
                    return True
        except Exception as e:
            print(f"{source_name} error for {p_id}: {e}")

    # 最后兜底：如果第一个源有数据，即使不新鲜也用它
    try:
        if 'first_source_items' in locals() and first_source_items:
            save_to_db(p_id, first_source_items, now_str)
            return True
    except: pass

    return False

    return False

def save_to_db(p_id, items, now_str):
    # 导出微博数据到指定目录
    if p_id == "weibo":
        try:
            # 解析时间
            dt = datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%Y%m%d")
            # 避免在 strftime 中使用中文，防止 Windows 下编码错误
            time_str = f"{dt.hour:02d}时{dt.minute:02d}分"
            
            # 构建保存路径: E:\JNU-OPORC\MediaCrawler\source\weibo\top\YYYYMMDD\HH时mm分.txt
            # 使用相对路径定位到 MediaCrawler 目录
            project_root = Path(__file__).resolve().parents[2]
            save_dir = project_root / "MediaCrawler" / "source" / "weibo" / "top" / date_str
            
            # 确保目录存在
            if not save_dir.exists():
                save_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = save_dir / f"{time_str}.json"
            
            data = {
                "type": "weibo",
                "update_time": now_str,
                "list": []
            }
            
            for index, item in enumerate(items, 1):
                url = item.get("url")
                if url:
                    data["list"].append({
                        "index": index,
                        "title": item.get("title", ""),
                        "url": url,
                        "hot_value": item.get("hot", ""),
                        "extra": {}
                    })
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"Exported Weibo data to {file_path}")
        except Exception as e:
            print(f"Error exporting Weibo data: {e}")

    # 增加 timeout 以处理并发写入时的 database locked 问题
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()
    
    # 1. 获取最近的几次抓取记录（用于对比趋势，解决 API 返回交替缓存数据的问题）
    cur.execute('SELECT DISTINCT fetch_time FROM hot_search_data WHERE platform = ? AND fetch_time < ? ORDER BY fetch_time DESC LIMIT 3', (p_id, now_str))
    last_times = [row[0] for row in cur.fetchall()]
    
    prev_ranks = {}
    if last_times:
        # 按时间倒序获取数据，越早的数据先存入，这样晚的数据（更接近当前的）会覆盖旧的
        for last_time in reversed(last_times):
            # 获取上一次的排名、趋势和原始排名
            cur.execute('SELECT title, rank, trend, previous_rank FROM hot_search_data WHERE platform = ? AND fetch_time = ?', (p_id, last_time))
            # 存储为 {清洗后的标题: (排名, 趋势, 上上次排名, 抓取时间)}
            rows = cur.fetchall()
            for row in rows:
                if row[0]:
                    c_t = clean_title(row[0])
                    prev_ranks[c_t] = (row[1], row[2], row[3], last_time)
            
        print(f"DEBUG: [save_to_db] Found previous cache for {p_id} from {len(last_times)} periods, total {len(prev_ranks)} items", flush=True)
    else:
        print(f"DEBUG: [save_to_db] No previous cache found for {p_id} to compare trends", flush=True)

    # 2. 清理同平台同时间戳数据（防止重复插入）
    cur.execute('DELETE FROM hot_search_data WHERE platform = ? AND fetch_time = ?', (p_id, now_str))
    
    # 3. 准备批量插入数据
    insert_data = []
    current_rank = 1
    debug_log_path = os.path.join(CACHE_DIR, f"debug_{p_id}.log")
    with open(debug_log_path, "a", encoding="utf-8") as f:
        f.write(f"\n--- Sync at {now_str} ---\n")
        f.write(f"Found previous cache from {len(last_times)} periods: {last_times}\n")
        
        for item in items[:100]:
            raw_title = str(item.get("title", "")).strip()
            if not raw_title: continue
            
            match_title = clean_title(raw_title)
            item_url = item.get("url") or item.get("mobileUrl") or "#"
            # 获取热度，如果不存在则设为 None 而不是 "0"
            hot = str(item.get("hot") or item.get("hot_value") or "")
            if hot == "0" or not hot:
                hot = None
            
            # 针对知乎 (zhihu) 平台热度进行修正
            # 如果热度小于 10000 且不是 None，可能是单位丢失，手动乘以 10000 补全
            # 774 -> 774万
            if p_id == 'zhihu' and hot and hot.isdigit():
                try:
                    hot_val = int(hot)
                    # 阈值设为 100000，小于 10 万的都认为是异常小的数据（知乎热度通常在百万级）
                    if hot_val < 100000:
                        hot = str(hot_val * 10000)
                except:
                    pass
            
            rank = current_rank
            current_rank += 1
            
            # 计算趋势
            prev_info = prev_ranks.get(match_title)
            trend = 0
            prev_rank_val = None
            
            if prev_info is not None:
                # prev_info is (rank, trend, previous_rank, fetch_time)
                last_rank, last_trend, last_prev_rank, last_time_src = prev_info
                prev_rank_val = last_rank
                try:
                    last_rank_int = int(last_rank)
                    if last_rank_int > rank:
                        trend = 1
                    elif last_rank_int < rank:
                        trend = -1
                    else:
                        # 继承上一次的趋势状态和原始排名
                        trend = int(last_trend) if last_trend is not None else 0
                        if trend != 0:
                            # 继承上一次的 previous_rank
                            prev_rank_val = last_prev_rank
                except (ValueError, TypeError):
                    pass
            
            # 兼容逻辑：如果没有匹配到标题，但在某些 API 中自带了排名变化信息
            if prev_rank_val is None and item.get("previous_rank"):
                try:
                    p_r = int(item.get("previous_rank"))
                    if p_r > 0:
                        prev_rank_val = p_r
                        if p_r > rank: trend = 1
                        elif p_r < rank: trend = -1
                except: pass

            is_new = 1 if prev_rank_val is None else 0
            
            f.write(f"Item {rank}: '{match_title}', prev: {prev_info if prev_info else 'None'}, trend: {trend}\n")

            insert_data.append((
                p_id, raw_title, item_url, hot, rank, now_str,
                prev_rank_val, trend, is_new
            ))
        
        f.write(f"Successfully inserted {len(insert_data)} items. New items: {sum(1 for d in insert_data if d[8] == 1)}\n")
    
    # 4. 批量执行插入
    if insert_data:
        cur.executemany('''
            INSERT INTO hot_search_data (platform, title, url, hot_value, rank, fetch_time, previous_rank, trend, is_new)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', insert_data)
        non_zero_trends = sum(1 for d in insert_data if d[7] != 0)
        print(f"DEBUG: [save_to_db] Successfully inserted {len(insert_data)} items for {p_id} at {now_str}. Trends: {non_zero_trends}, New: {sum(1 for d in insert_data if d[8] == 1)}", flush=True)
        conn.commit()
        conn.close()
        return non_zero_trends
    else:
        print(f"DEBUG: [save_to_db] No data to insert for {p_id}", flush=True)
        conn.commit()
        conn.close()
        return 0

def sync_platform_data(p_id, now_str, source=None, skip_sleep=False):
    """同步平台数据的后台任务 (优先使用实时 API)"""
    
    # 只有在非手动刷新且非静默后台更新时才添加随机延迟
    if not skip_sleep:
        time.sleep(random.uniform(0.5, 2.0))
    
    # 1. 优先尝试实时 API 获取 (不依赖文件，更及时)
    try:
        if sync_platform_data_live(p_id, now_str, preferred_source=source):
            return True
    except Exception as e:
        print(f"Error in sync_platform_data_live for {p_id}: {e}")
        
    # 2. 如果实时 API 失败，尝试 TrendRadar 的本地缓存 (DataQueryTools)
    try:
        if sync_platform_data_from_trendradar(p_id, now_str):
            return True
    except Exception as e:
        print(f"Error in sync_platform_data_from_trendradar for {p_id}: {e}")
                
    return False

@router.get("/platforms")
async def get_hotsearch_platforms(all: bool = False):
    """获取支持的热搜平台。all=True 返回所有可用平台，否则返回默认展示平台。"""
    if all:
        return ALL_PLATFORMS
    return PLATFORM_NAMES

@router.get("/all")
async def get_all_hotsearch_data(background_tasks: BackgroundTasks, refresh: bool = False, source: str = None, all_platforms: bool = False):
    """获取热搜数据。
    refresh: 是否强制实时抓取
    source: 指定 API 数据源 (1 或 2)
    all_platforms: True 则返回所有平台(ALL_PLATFORMS)，False 则仅返回默认平台(PLATFORM_NAMES)
    """
    if all_platforms:
        platforms = ALL_PLATFORMS
    else:
        platforms = PLATFORM_NAMES
    
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    # 设置缓存阈值为 30 分钟
    cache_threshold = (now_dt - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    
    # 如果是强制刷新，同步并行执行所有平台的抓取
    if refresh:
        print(f"Starting synchronous parallel refresh for all {len(platforms)} platforms using source: {source}...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(platforms), 10)) as executor:
            # 提交所有抓取任务 (跳过随机延迟)
            future_to_platform = {executor.submit(sync_platform_data, p["id"], now_str, source, skip_sleep=True): p["id"] for p in platforms}
            # 等待所有任务完成（设置 8 秒超时，防止某 API 极慢导致整体挂起）
            done, not_done = concurrent.futures.wait(future_to_platform.keys(), timeout=8)
            print(f"Parallel refresh completed: {len(done)} finished, {len(not_done)} timed out.")
    
    results = []
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Optimize: Get latest data for all platforms in a single query
    # First, identify the target platforms we want
    target_p_ids = [p["id"] for p in platforms]
    
    # Use a dictionary to map platform ID to its config for easy access
    platform_map = {p["id"]: p for p in platforms}
    
    # Query to get the latest fetch_time for each platform
    # We filter by the platforms we are interested in
    placeholders = ','.join(['?'] * len(target_p_ids))
    cur.execute(f'''
        SELECT platform, MAX(fetch_time) as max_time 
        FROM hot_search_data 
        WHERE platform IN ({placeholders}) 
        GROUP BY platform
    ''', target_p_ids)
    
    latest_times = {row['platform']: row['max_time'] for row in cur.fetchall()}
    
    # Prepare to collect data
    # We can fetch all data for these latest times in one go
    # But since we need to structure it by platform, we can just fetch all rows and process in Python
    # OR we can iterate (now that we have the timestamp, the query is fast)
    # Fetching all might be better to avoid N queries
    
    all_data_map = {}
    if latest_times:
        # Construct a query to get data for these specific (platform, time) pairs
        # Since SQLite tuple IN might be slow or not supported in old versions, 
        # let's just query where platform IN (...) AND fetch_time >= min(latest_times)
        # and then filter in Python. Or just query all data for these platforms that matches the specific time.
        
        # A simple approach that is robust:
        # SELECT * FROM hot_search_data WHERE platform = ? AND fetch_time = ?
        # executing this N times is actually fast if indexed.
        # But let's try to reduce it.
        
        # Let's use: WHERE (platform = 'a' AND fetch_time = 't1') OR (platform = 'b' AND fetch_time = 't2') ...
        # This can be constructed dynamically.
        
        criteria = []
        params = []
        for pid, time_str in latest_times.items():
            criteria.append("(platform = ? AND fetch_time = ?)")
            params.extend([pid, time_str])
            
        if criteria:
            query = f"SELECT * FROM hot_search_data WHERE {' OR '.join(criteria)} ORDER BY platform, rank ASC"
            cur.execute(query, params)
            rows = cur.fetchall()
            
            for row in rows:
                pid = row['platform']
                if pid not in all_data_map:
                    all_data_map[pid] = []
                all_data_map[pid].append(row)

    # Process results
    for p_id in target_p_ids:
        p_name = platform_map[p_id]["name"]
        
        platform_result = {
            "id": p_id,
            "name": p_name,
            "data": [],
            "status": "loading", # Default to loading if no data found
            "error": None,
            "fetch_time": now_str
        }
        
        if p_id in latest_times:
            last_time = latest_times[p_id]
            platform_rows = all_data_map.get(p_id, [])
            
            platform_result["data"] = [
                {
                    "title": r["title"], 
                    "url": r["url"], 
                    "hot": r["hot_value"] if p_id not in ['thepaper', 'toutiao'] else None, 
                    "rank": r["rank"],
                    "trend": int(r["trend"]) if r["trend"] is not None else 0,
                    "previous_rank": r["previous_rank"],
                    "is_new": bool(r["is_new"])
                } for r in platform_rows
            ]
            platform_result["fetch_time"] = last_time
            platform_result["status"] = "cached" if last_time > cache_threshold else "history"
            
            # Check if stale
            if not refresh and last_time <= cache_threshold:
                background_tasks.add_task(sync_platform_data, p_id, now_str, source)
                platform_result["status"] = "refreshing"
        else:
            # No data found
             if not refresh:
                background_tasks.add_task(sync_platform_data, p_id, now_str, source)
                platform_result["status"] = "loading"
             else:
                platform_result["status"] = "error"
                platform_result["error"] = "抓取失败"
        
        results.append(platform_result)
        
    conn.close()
    return results

def check_and_sync_missing_data():
    """系统启动时检查所有平台数据完整性，缺失则补全"""
    print("Checking data integrity for all platforms...")
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    # 设置 30 分钟内的缓存为有效
    cache_threshold = (now_dt - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    
    platforms = ALL_PLATFORMS
    missing_platforms = []
    
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cur = conn.cursor()
    
    for p in platforms:
        p_id = p["id"]
        # 检查是否有 10 分钟内的最新数据
        cur.execute('SELECT 1 FROM hot_search_data WHERE platform = ? AND fetch_time > ? LIMIT 1', (p_id, cache_threshold))
        if not cur.fetchone():
            missing_platforms.append(p_id)
            
    conn.close()
    
    if missing_platforms:
        print(f"Detected {len(missing_platforms)} platforms with missing or stale data: {missing_platforms}")
        print("Starting background synchronization...")
        # 并行执行缺失平台的抓取
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(missing_platforms), 10)) as executor:
            executor.map(lambda p_id: sync_platform_data(p_id, now_str), missing_platforms)
        print("Data integrity check and synchronization completed.")
    else:
        print("All platforms have recent data. No synchronization needed.")

@router.get("/refresh/{platform_id}")
async def refresh_platform_data(platform_id: str, background_tasks: BackgroundTasks):
    """手动触发单个平台的数据更新并同步返回最新结果"""
    platforms = await get_hotsearch_platforms(all=True)
    p = next((x for x in platforms if x["id"] == platform_id), None)
    if not p:
        raise HTTPException(status_code=404, detail="Platform not found")
        
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # 同步执行抓取并等待 (跳过随机延迟)
    print(f"Refreshing single platform {platform_id} synchronously...")
    success = sync_platform_data(platform_id, now_str, skip_sleep=True)
    
    # 4. 返回最新抓取到的数据
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    platform_result = {
        "id": platform_id,
        "name": p["name"],
        "data": [],
        "status": "success" if success else "error",
        "error": None if success else "API fetch failed",
        "fetch_time": now_str
    }
    
    # 再次查询最新数据
    cur.execute('SELECT DISTINCT fetch_time FROM hot_search_data WHERE platform = ? ORDER BY fetch_time DESC LIMIT 1', (platform_id,))
    last_time_row = cur.fetchone()
    if last_time_row:
        last_time = last_time_row[0]
        cur.execute('SELECT * FROM hot_search_data WHERE platform = ? AND fetch_time = ? ORDER BY rank ASC', (platform_id, last_time))
        platform_result["data"] = [
            {
                "title": r["title"], 
                "url": r["url"], 
                "hot": r["hot_value"] if platform_id not in ['thepaper', 'toutiao'] else None, 
                "rank": r["rank"],
                "trend": int(r["trend"]) if r["trend"] is not None else 0,
                "previous_rank": r["previous_rank"],
                "is_new": bool(r["is_new"])
            } for r in cur.fetchall()
        ]
        platform_result["fetch_time"] = last_time
        platform_result["status"] = "cached"
        
    conn.close()
    return platform_result

@router.get("/data/{platform_id}")
async def get_hotsearch_data(platform_id: str):
    """获取指定平台的热搜数据"""
    api_p_id = SOURCE2_PLATFORMS.get(platform_id, platform_id)
    url = HOTSEARCH_SOURCES["source2"].format(platform=api_p_id, timestamp=int(time.time()))
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        if data.get("status") in ["success", "cache"]:
            # 过滤热度显示
            if platform_id in ['thepaper', 'toutiao'] and "data" in data:
                for item in data["data"]:
                    if "hot" in item:
                        item["hot"] = None
            return data
        else:
            raise HTTPException(status_code=500, detail=f"API Error: {data.get('status')}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/favorites")
async def get_favorites(user: User = Depends(get_current_user)):
    rows = query_db("SELECT platform_id FROM user_platform_follows WHERE user_id = ?", (user.id,))
    if not rows:
        return []
    return [row['platform_id'] for row in rows]

@router.post("/favorites/{platform_id}")
async def add_favorite(platform_id: str, user: User = Depends(get_current_user)):
    try:
        # Check if already exists
        exists = query_db("SELECT 1 FROM user_platform_follows WHERE user_id = ? AND platform_id = ?", 
                          (user.id, platform_id), one=True)
        if exists:
            return {"message": "Already in favorites"}
            
        success = execute_db("INSERT INTO user_platform_follows (user_id, platform_id) VALUES (?, ?)", 
                   (user.id, platform_id))
        if not success:
            raise HTTPException(status_code=500, detail="Database write failed")
        return {"message": "Added to favorites"}
    except Exception as e:
        print(f"Error adding favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/favorites/{platform_id}")
async def remove_favorite(platform_id: str, user: User = Depends(get_current_user)):
    success = execute_db("DELETE FROM user_platform_follows WHERE user_id = ? AND platform_id = ?", 
               (user.id, platform_id))
    if not success:
        raise HTTPException(status_code=500, detail="Database write failed")
    return {"message": "Removed from favorites"}
