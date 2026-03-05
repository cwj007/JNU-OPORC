import aiosqlite
import httpx
import json
import urllib3
import re
import sys
import os
import time
import random
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from .database import DB_PATH, CACHE_DIR, query_db, execute_db, get_target_db
from .auth import get_current_user, User
from .config import SOURCE1_PLATFORMS, SOURCE2_PLATFORMS, PLATFORM_NAMES, ALL_PLATFORMS, HOTSEARCH_SOURCES, PRIORITY_PLATFORMS

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

# 创建全局 httpx AsyncClient 以复用连接
async_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(15.0, connect=5.0),
    verify=False,
    limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)
)

router = APIRouter(prefix="/hotsearch", tags=["hotsearch"])

async def sync_platform_data_from_trendradar(p_id, now_str):
    """从 TrendRadar 的 API/本地数据 同步数据"""
    if not trendradar_tools:
        return False
        
    try:
        # 映射平台 ID（Visualized ID -> TrendRadar ID）
        id_mapping = {}
        tr_p_id = id_mapping.get(p_id, p_id)
        
        # 调用 TrendRadar 的最新数据接口 (假设它是同步的，暂时用 run_in_executor 包装，或者如果它本身是异步的就 await)
        # 注意：这里我们无法直接修改 trendradar_tools，所以假设它是同步阻塞的
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: trendradar_tools.get_latest_news(platforms=[tr_p_id], limit=100, include_url=True))
        
        if result.get("success") and result.get("news"):
            news_items = result["news"]
            # 使用统一的 save_to_db 处理趋势和批量插入
            await save_to_db(p_id, news_items, now_str)
            print(f"Successfully synced {p_id} from TrendRadar API with trend")
            return True
            
        return False
    except Exception as e:
        print(f"Error syncing {p_id} from TrendRadar: {e}")
        return False

async def start_periodic_sync():
    """启动周期性数据同步任务"""
    counter = 0
    while True:
        try:
            # 默认每 10 分钟同步一次优先平台
            # 每 30 分钟同步一次所有平台 (即每 3 个 10 分钟周期)
            if counter % 3 == 0:
                print(f"[{datetime.now()}] Starting scheduled background sync for ALL platforms...")
                await sync_all_platforms()
            else:
                print(f"[{datetime.now()}] Starting scheduled background sync for PRIORITY platforms...")
                # 通过 only_priority 参数仅同步重要平台
                await sync_all_platforms(only_priority=True)
            
            print(f"[{datetime.now()}] Scheduled background sync completed.")
        except Exception as e:
            print(f"Error in background sync: {e}")
        
        counter += 1
        # 调整为每 10 分钟运行一次
        await asyncio.sleep(10 * 60)

# 并行任务限制：控制并发抓取的数量
MAX_CONCURRENT_SYNC = 8  # 增加并发数以提高抓取效率
sync_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SYNC)

async def sync_all_platforms(only_priority=False):
    """同步所有平台的数据 (两个 API 源的所有平台)"""
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # 根据 priority 参数过滤平台
    if only_priority:
        # 只包含在 PRIORITY_PLATFORMS 中的平台
        platforms = [p for p in ALL_PLATFORMS if p["id"] in PRIORITY_PLATFORMS]
    else:
        # 同步所有平台，但把优先平台排在前面
        priority = [p for p in ALL_PLATFORMS if p["id"] in PRIORITY_PLATFORMS]
        others = [p for p in ALL_PLATFORMS if p["id"] not in PRIORITY_PLATFORMS]
        platforms = priority + others
    
    print(f"Syncing {len(platforms)} platforms in background (only_priority={only_priority}, concurrency={MAX_CONCURRENT_SYNC})...")
    
    async def limited_sync(p):
        async with sync_semaphore:
            # 优先平台不进行随机等待，实现“快速获取”
            is_priority = p["id"] in PRIORITY_PLATFORMS
            return await sync_platform_data(p["id"], now_str, skip_sleep=is_priority)

    # 使用 asyncio.gather 并行执行抓取任务，但受信号量限制
    tasks = [limited_sync(p) for p in platforms]
    await asyncio.gather(*tasks, return_exceptions=True)

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

async def get_last_titles(p_id):
    """获取该平台最近一次抓取的清洗后的标题列表，用于判断 API 数据是否刷新"""
    try:
        row = await query_db('SELECT fetch_time FROM hot_search_data WHERE platform = ? ORDER BY fetch_time DESC LIMIT 1', (p_id,), one=True)
        if not row:
            return []
        
        last_time = row['fetch_time']
        rows = await query_db('SELECT title FROM hot_search_data WHERE platform = ? AND fetch_time = ? ORDER BY rank ASC', (p_id, last_time))
        titles = [clean_title(r['title']) for r in rows]
        return titles
    except Exception as e:
        print(f"Error getting last titles for {p_id}: {e}")
        return []

async def sync_platform_data_live(p_id, now_str, preferred_source=None):
    """直接从 API 获取实时数据并存入 SQLite，带重试和多源兜底机制"""
    # 分别获取两个源对应的平台 ID
    s1_api_p_id = SOURCE1_PLATFORMS.get(p_id, p_id)
    s2_api_p_id = SOURCE2_PLATFORMS.get(p_id, p_id)
    
    # 获取上一次抓取的内容，用于去重/判断刷新
    last_cleaned_titles = await get_last_titles(p_id)
    
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
    else:        sources_to_try = [
            ("source1", source1_url, s1_api_p_id),
            ("source2", source2_url, s2_api_p_id)
        ]

    # 针对优先平台使用更短的超时时间，以实现“快速获取”
    is_priority = p_id in PRIORITY_PLATFORMS
    current_timeout = 8.0 if is_priority else 15.0

    for source_name, url, api_p_id in sources_to_try:
        try:
            print(f"Fetching from {source_name} for {p_id} (timeout={current_timeout}s)")
            res = await async_http_client.get(url, headers=headers, timeout=current_timeout)
            if res.status_code == 200:
                data = res.json()
                items = []
                if source_name == "source1":
                    items_raw = data.get("data") or data.get("list") or []
                    for item in items_raw[:100]:
                        # 尝试从多个字段获取热度值
                        hot_val = item.get("hot") or item.get("hot_value") or item.get("hotValue") or item.get("heat") or item.get("index") or ""
                        
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
                    await save_to_db(p_id, items, now_str)
                    return True
        except Exception as e:
            print(f"{source_name} error for {p_id}: {e}")

    return False

async def save_to_db(p_id, items, now_str):
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
    target_db = get_target_db("hot_search_data")
    async with aiosqlite.connect(target_db, timeout=30) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.cursor()
        
        # 1. 获取最近的几次抓取记录（用于对比趋势，解决 API 返回交替缓存数据的问题）
        await cur.execute('SELECT DISTINCT fetch_time FROM hot_search_data WHERE platform = ? AND fetch_time < ? ORDER BY fetch_time DESC LIMIT 3', (p_id, now_str))
        last_times = [row[0] for row in await cur.fetchall()]
        
        prev_ranks = {}
        if last_times:
            # 按时间倒序获取数据，越早的数据先存入，这样晚的数据（更接近当前的）会覆盖旧의
            for last_time in reversed(last_times):
                # 获取上一次的排名、趋势和原始排名
                await cur.execute('SELECT title, rank, trend, previous_rank FROM hot_search_data WHERE platform = ? AND fetch_time = ?', (p_id, last_time))
                # 存储为 {清洗后的标题: (排名, 趋势, 上上次排名, 抓取时间)}
                rows = await cur.fetchall()
                for row in rows:
                    if row[0]:
                        c_t = clean_title(row[0])
                        prev_ranks[c_t] = (row[1], row[2], row[3], last_time)
                
            print(f"DEBUG: [save_to_db] Found previous cache for {p_id} from {len(last_times)} periods, total {len(prev_ranks)} items", flush=True)
        else:
            print(f"DEBUG: [save_to_db] No previous cache found for {p_id} to compare trends", flush=True)

        # 2. 清理同平台同时间戳数据（防止重复插入）
        await cur.execute('DELETE FROM hot_search_data WHERE platform = ? AND fetch_time = ?', (p_id, now_str))
        
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
                if p_id == 'zhihu' and hot and hot.isdigit():
                    try:
                        hot_val = int(hot)
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
                    last_rank, last_trend, last_prev_rank, last_time_src = prev_info
                    prev_rank_val = last_rank
                    try:
                        last_rank_int = int(last_rank)
                        if last_rank_int > rank:
                            trend = 1
                        elif last_rank_int < rank:
                            trend = -1
                        else:
                            trend = int(last_trend) if last_trend is not None else 0
                            if trend != 0:
                                prev_rank_val = last_prev_rank
                    except (ValueError, TypeError):
                        pass
                
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
            await cur.executemany('''
                INSERT INTO hot_search_data (platform, title, url, hot_value, rank, fetch_time, previous_rank, trend, is_new)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', insert_data)
            await conn.commit()
            non_zero_trends = sum(1 for d in insert_data if d[7] != 0)
            print(f"DEBUG: [save_to_db] Successfully inserted {len(insert_data)} items for {p_id} at {now_str}. Trends: {non_zero_trends}, New: {sum(1 for d in insert_data if d[8] == 1)}", flush=True)
            return non_zero_trends
        else:
            print(f"DEBUG: [save_to_db] No data to insert for {p_id}", flush=True)
            return 0

async def sync_platform_data(p_id, now_str, source=None, skip_sleep=False):
    """同步平台数据的后台任务 (优先使用实时 API)"""
    
    # 只有在非手动刷新且非静默后台更新时才添加随机延迟
    if not skip_sleep:
        await asyncio.sleep(random.uniform(0.5, 2.0))
    
    # 1. 优先尝试实时 API 获取 (不依赖文件，更及时)
    try:
        if await sync_platform_data_live(p_id, now_str, preferred_source=source):
            return True
    except Exception as e:
        print(f"Error in sync_platform_data_live for {p_id}: {e}")
        
    # 2. 如果实时 API 失败，尝试 TrendRadar 的本地缓存 (DataQueryTools)
    try:
        if await sync_platform_data_from_trendradar(p_id, now_str):
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
        # 获取所有平台，但优先把 PRIORITY_PLATFORMS 排在前面
        priority = [p for p in ALL_PLATFORMS if p["id"] in PRIORITY_PLATFORMS]
        others = [p for p in ALL_PLATFORMS if p["id"] not in PRIORITY_PLATFORMS]
        platforms = priority + others
    else:
        # 默认展示平台也按照优先级排序
        priority = [p for p in PLATFORM_NAMES if p["id"] in PRIORITY_PLATFORMS]
        others = [p for p in PLATFORM_NAMES if p["id"] not in PRIORITY_PLATFORMS]
        platforms = priority + others
    
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    # 设置缓存阈值为 30 分钟
    cache_threshold = (now_dt - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    
    # 如果是强制刷新，同步并行执行所有平台的抓取
    if refresh:
        print(f"Starting async parallel refresh for all {len(platforms)} platforms using source: {source} (concurrency={MAX_CONCURRENT_SYNC})...")
        
        async def limited_sync(p):
            async with sync_semaphore:
                return await sync_platform_data(p["id"], now_str, source, skip_sleep=True)

        # 并行执行抓取任务 (受信号量限制)
        tasks = [limited_sync(p) for p in platforms]
        # 等待所有任务完成
        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"Parallel refresh completed.")
    
    results = []
    
    # Optimize: Get latest data for all platforms in a single query
    # First, identify the target platforms we want
    target_p_ids = [p["id"] for p in platforms]
    
    # Use a dictionary to map platform ID to its config for easy access
    platform_map = {p["id"]: p for p in platforms}
    
    # Query to get the latest fetch_time for each platform
    # We filter by the platforms we are interested in
    placeholders = ','.join(['?'] * len(target_p_ids))
    latest_times_rows = await query_db(f'''
        SELECT platform, MAX(fetch_time) as max_time 
        FROM hot_search_data 
        WHERE platform IN ({placeholders}) 
        GROUP BY platform
    ''', tuple(target_p_ids))
    
    latest_times = {row['platform']: row['max_time'] for row in latest_times_rows} if latest_times_rows else {}
    
    # Prepare to collect data
    all_data_map = {}
    if latest_times:
        criteria = []
        params = []
        for pid, time_str in latest_times.items():
            criteria.append("(platform = ? AND fetch_time = ?)")
            params.extend([pid, time_str])
            
        if criteria:
            query = f"SELECT * FROM hot_search_data WHERE {' OR '.join(criteria)} ORDER BY platform, rank ASC"
            rows = await query_db(query, tuple(params))
            
            if rows:
                for row in rows:
                    pid = row['platform']
                    if pid not in all_data_map:
                        all_data_map[pid] = []
                    all_data_map[pid].append(row)

    # Process results
    for p_id in target_p_ids:
        p_name = platform_map[p_id]["name"]
        
        # 针对优先平台设置更短的缓存有效期 (10分钟)，非优先平台维持 30分钟
        is_priority = p_id in PRIORITY_PLATFORMS
        current_cache_threshold = (now_dt - timedelta(minutes=10 if is_priority else 30)).strftime("%Y-%m-%d %H:%M:%S")
        
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
            platform_result["status"] = "cached" if last_time > current_cache_threshold else "history"
            
            # Check if stale
            if not refresh and last_time <= current_cache_threshold:
                background_tasks.add_task(sync_platform_data, p_id, now_str, source, skip_sleep=is_priority)
                platform_result["status"] = "refreshing"
        else:
            # No data found
             if not refresh:
                background_tasks.add_task(sync_platform_data, p_id, now_str, source, skip_sleep=is_priority)
                platform_result["status"] = "loading"
             else:
                platform_result["status"] = "error"
                platform_result["error"] = "抓取失败"
        
        results.append(platform_result)
        
    return results

async def check_and_sync_missing_data():
    """系统启动时检查所有平台数据完整性，缺失则补全"""
    print("Checking data integrity for all platforms...")
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    platforms = ALL_PLATFORMS
    missing_platforms = []
    
    for p in platforms:
        p_id = p["id"]
        is_priority = p_id in PRIORITY_PLATFORMS
        # 优先平台 10 分钟缓存，普通平台 30 分钟
        threshold = (now_dt - timedelta(minutes=10 if is_priority else 30)).strftime("%Y-%m-%d %H:%M:%S")
        
        row = await query_db('SELECT MAX(fetch_time) as max_time FROM hot_search_data WHERE platform = ?', (p_id, ), one=True)
        if not row or not row['max_time'] or row['max_time'] <= threshold:
            missing_platforms.append(p)
    
    if missing_platforms:
        print(f"Found {len(missing_platforms)} platforms with missing or stale data. Syncing...")
        # 分批并行同步
        async def limited_sync(p):
            async with sync_semaphore:
                is_priority = p["id"] in PRIORITY_PLATFORMS
                return await sync_platform_data(p["id"], now_str, skip_sleep=is_priority)

        tasks = [limited_sync(p) for p in missing_platforms]
        await asyncio.gather(*tasks, return_exceptions=True)
        print("Initial data sync completed.")
    else:
        print("All platforms have up-to-date data.")

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
    success = await sync_platform_data(platform_id, now_str, skip_sleep=True)
    
    platform_result = {
        "id": platform_id,
        "name": p["name"],
        "data": [],
        "status": "success" if success else "error",
        "error": None if success else "API fetch failed",
        "fetch_time": now_str
    }
    
    # 再次查询最新数据
    last_time_row = await query_db('SELECT DISTINCT fetch_time FROM hot_search_data WHERE platform = ? ORDER BY fetch_time DESC LIMIT 1', (platform_id,), one=True)
    if last_time_row:
        last_time = last_time_row['fetch_time']
        rows = await query_db('SELECT * FROM hot_search_data WHERE platform = ? AND fetch_time = ? ORDER BY rank ASC', (platform_id, last_time))
        if rows:
            platform_result["data"] = [
                {
                    "title": r["title"], 
                    "url": r["url"], 
                    "hot": r["hot_value"] if platform_id not in ['thepaper', 'toutiao'] else None, 
                    "rank": r["rank"],
                    "trend": int(r["trend"]) if r["trend"] is not None else 0,
                    "previous_rank": r["previous_rank"],
                    "is_new": bool(r["is_new"])
                } for r in rows
            ]
            platform_result["fetch_time"] = last_time
            platform_result["status"] = "cached"
        
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
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            response = await client.get(url, headers=headers)
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
    rows = await query_db("SELECT platform_id FROM user_platform_follows WHERE user_id = ?", (user.id,))
    if not rows:
        return []
    return [row['platform_id'] for row in rows]

@router.post("/favorites/{platform_id}")
async def add_favorite(platform_id: str, user: User = Depends(get_current_user)):
    try:
        # Check if already exists
        exists = await query_db("SELECT 1 FROM user_platform_follows WHERE user_id = ? AND platform_id = ?", 
                          (user.id, platform_id), one=True)
        if exists:
            return {"message": "Already in favorites"}
            
        success = await execute_db("INSERT INTO user_platform_follows (user_id, platform_id) VALUES (?, ?)", 
                   (user.id, platform_id))
        if not success:
            raise HTTPException(status_code=500, detail="Database write failed")
        return {"message": "Added to favorites"}
    except Exception as e:
        print(f"Error adding favorite: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/favorites/{platform_id}")
async def remove_favorite(platform_id: str, user: User = Depends(get_current_user)):
    success = await execute_db("DELETE FROM user_platform_follows WHERE user_id = ? AND platform_id = ?", 
               (user.id, platform_id))
    if not success:
        raise HTTPException(status_code=500, detail="Database write failed")
    return {"message": "Removed from favorites"}
