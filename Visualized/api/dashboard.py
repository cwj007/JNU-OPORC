import json
import math
from typing import Optional, Any, List, Dict, Tuple, Union
import jieba
import jieba.analyse
import re
from collections import Counter
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from .database import query_db
from .utils import is_junk_label
from .common import PLATFORM_MAP, parse_keyword_expr, build_date_filter, parse_date_string
from .auth import get_current_user, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

async def build_task_filter(task_id: int, current_user: User, table_alias: str = None, mode: str = "full"):
    """根据任务 ID 构造 SQL 过滤条件，并校验用户权限"""
    # 权限控制：普通用户只能看到自己任务范围内的数据
    user_tasks = []
    if current_user.role != 'admin':
        if task_id:
            # 校验特定任务是否属于该用户
            task = await query_db("SELECT id, name, keywords, exclude_words, platforms, warning_keywords FROM monitoring_tasks WHERE id = ? AND user_id = ?", (task_id, current_user.id), one=True)
            if not task:
                return "1=0", [] # 无权限
            user_tasks = [task]
        else:
            # 非管理员且未指定任务：允许查看全局数据（与 monitoring.py 逻辑一致）
            return "", []
    else:
        # 管理员可以看所有，但如果指定了 task_id，则只看该任务
        if task_id:
            task = await query_db("SELECT id, name, keywords, exclude_words, platforms, warning_keywords FROM monitoring_tasks WHERE id = ?", (task_id,), one=True)
            if not task:
                return "1=0", []
            user_tasks = [task]
        else:
            # 管理员且未指定任务，返回空过滤条件表示查看全部
            return "", []

    # 构造过滤条件 (逻辑同 monitoring.py 的 build_user_scope_filter)
    or_groups = []
    all_params = []
    alias = f"{table_alias}." if table_alias else ""

    for t in user_tasks:
        task_clauses = []
        task_params = []
        
        # 1. Keywords
        if t.get('keywords'):
            # 暂时禁用 FTS5，改用 LIKE
            k_sql, k_params = parse_keyword_expr(t['keywords'], mode=mode, table_alias=table_alias, use_fts=False)
            if k_sql:
                task_clauses.append(k_sql)
                task_params.extend(k_params)
        
        # 2. Platforms
        if t.get('platforms'):
            p_clauses = []
            p_list = t['platforms'].split(',')
            for p in p_list:
                if not p.strip(): continue
                p_str = p.strip()
                search_terms = [p_str]
                if p_str in PLATFORM_MAP:
                    search_terms.append(PLATFORM_MAP[p_str])
                
                p_or = []
                for term in search_terms:
                    p_or.append(f"{alias}source LIKE ?")
                    task_params.append(f"%{term}%")
                p_clauses.append(f"({' OR '.join(p_or)})")
            
            if p_clauses:
                task_clauses.append(f"({' OR '.join(p_clauses)})")
        
        # 3. Exclude
        if t.get('exclude_words'):
            excludes = t['exclude_words'].replace(',', ' ').split()
            for ew in excludes:
                if not ew.strip(): continue
                ew_wild = f"%{ew.strip()}%"
                if table_alias == 'cm' or mode == 'content':
                    task_clauses.append(f"({alias}content NOT LIKE ?)")
                    task_params.append(ew_wild)
                else:
                    if table_alias == 'c':
                        task_clauses.append(f"NOT ({alias}title LIKE ? OR {alias}content LIKE ? OR EXISTS (SELECT 1 FROM top_topics tt WHERE tt.top_id = {alias}top_id AND tt.top_name LIKE ?))")
                        task_params.extend([ew_wild, ew_wild, ew_wild])
                    else:
                        task_clauses.append(f"({alias}title NOT LIKE ? AND {alias}content NOT LIKE ?)")
                        task_params.extend([ew_wild, ew_wild])

        if task_clauses:
            or_groups.append(f"({' AND '.join(task_clauses)})")
            all_params.extend(task_params)

    if not or_groups:
        return "1=0", []
        
    final_sql = f"({' OR '.join(or_groups)})"
    return final_sql, all_params


@router.get("/tasks")
async def get_dashboard_tasks(current_user: User = Depends(get_current_user)):
    """获取所有监控任务列表，用于下拉选择"""
    try:
        if current_user.role == 'admin':
            tasks = await query_db("SELECT id, name FROM monitoring_tasks ORDER BY id DESC")
        else:
            tasks = await query_db("SELECT id, name FROM monitoring_tasks WHERE user_id = ? ORDER BY id DESC", (current_user.id,))
        return {"tasks": tasks, "status": "success"}
    except Exception as e:
        return {"tasks": [], "status": "error", "message": str(e)}

@router.get("/comments")
async def get_dashboard_comments(limit: int = 50, task_id: int = None, current_user: User = Depends(get_current_user)):
    """获取最新评论流，支持任务筛选"""
    try:
        where_clauses = ["cm.comment_id != '0'", "cm.source IS NOT NULL", "cm.source != ''"]
        params = []
        
        if task_id:
            # 统一使用 comments 表
            task_sql, task_params = await build_task_filter(task_id, current_user, table_alias='cm', mode='content')
            if task_sql:
                where_clauses.append(task_sql)
                params.extend(task_params)

        sql = f"""
            SELECT 
                comment_id, content, author, created_at, source, 
                sentiment, fine_grained_sentiment 
            FROM comments cm 
            WHERE {" AND ".join(where_clauses)}
            ORDER BY created_at DESC 
            LIMIT ?
        """
        params.append(limit)
        comments = await query_db(sql, tuple(params))
        
        results = []
        if comments:
            for c in comments:
                # Map sentiment to type for frontend styling
                s_type = "neutral"
                if c['sentiment'] == '正面':
                    s_type = "positive"
                elif c['sentiment'] == '负面':
                    s_type = "negative"
                
                # Platform mapping
                # The frontend expects platform codes like 'weibo', 'zhihu', etc.
                platform_map = {
                    "微博": "weibo",
                    "知乎": "zhihu",
                    "抖音": "douyin",
                    "快手": "kuaishou",
                    "B站": "bilibili",
                    "哔哩哔哩": "bilibili",
                    "小红书": "xhs",
                    "今日头条": "toutiao",
                    "百度": "baidu",
                    "网易": "netease",
                    "网易新闻": "netease",
                    "网易云音乐": "netease_music",
                    "36氪": "36kr",
                    "AcFun": "acfun",
                    "CSDN": "csdn",
                    "豆瓣": "douban",
                    "果壳": "guokr",
                    "虎扑": "hupu",
                    "虎嗅": "huxiu",
                    "凤凰": "ifeng",
                    "凤凰新闻": "ifeng",
                    "爱奇艺": "iqiyi",
                    "简书": "jianshu",
                    "掘金": "juejin",
                    "NGA": "nga",
                    "QQ音乐": "qqmusic",
                    "腾讯新闻": "qqnews",
                    "少数派": "sspai",
                    "Steam": "steam",
                    "澎湃": "thepaper",
                    "澎湃新闻": "thepaper",
                    "V2EX": "v2ex",
                    "腾讯视频": "v_qq",
                    "微信读书": "weread",
                    "GitHub": "github",
                    "原神": "genshin",
                    "崩坏3": "honkai3",
                    "星穹铁道": "starrail",
                    "英雄联盟": "lol",
                    "地震预警": "earthquake"
                }
                # Default to lowercase source if not in map, or keep as is if no match
                platform_code = platform_map.get(c['source'], c['source'].lower() if c['source'] else "other")
                
                results.append({
                    "id": c['comment_id'],
                    "author": c['author'] or "匿名用户",
                    "content": c['content'],
                    "platform": platform_code,
                    "sentiment": c['sentiment'],
                    "sentiment_type": s_type,
                    "time": c['created_at']
                })
        
        return {"comments": results, "status": "success"}
    except Exception as e:
        print(f"Error in get_dashboard_comments: {e}")
        return {"comments": [], "status": "error", "message": str(e)}

@router.get("/stats")
async def get_dashboard_stats(
    days: Any = 7, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    task_id: int = None, 
    current_user: User = Depends(get_current_user)
):
    """获取核心指标卡片数据，支持日期范围和任务筛选"""
    try:
        # 今日统计：以 sync_date 为准
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 趋势与分布统计：以 created_at 为准
        where_total_art, params_total_art = await build_date_filter(days, start_date, end_date, table_alias="c")
        where_total_cm, params_total_cm = await build_date_filter(days, start_date, end_date)
        
        # 构造任务过滤条件
        task_where_art, task_params_art = await build_task_filter(task_id, current_user, table_alias="c", mode="full")
        task_where_cm, task_params_cm = await build_task_filter(task_id, current_user, mode="content")
        
        # 1. 统计今日新增（统一使用过去 24 小时作为“今日新增”的口径，确保在 3/7/31 天视图下也一致）
        today_start_dt = datetime.now() - timedelta(days=1)
        today_start_str = today_start_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        where_today_art = ["c.created_at >= ?"]
        where_today_cm = ["created_at >= ?"]
        
        params_today_art = [today_start_str]
        if task_where_art and task_where_art != "":
            where_today_art.append(task_where_art)
            params_today_art.extend(task_params_art)
            
        sql_today_art = f"SELECT COUNT(*) as count FROM content c WHERE {' AND '.join(where_today_art)}"
        
        params_today_cm = [today_start_str]
        if task_where_cm and task_where_cm != "":
            where_today_cm.append(task_where_cm)
            params_today_cm.extend(task_params_cm)
            
        sql_today_cm = f"SELECT COUNT(*) as count FROM comments WHERE {' AND '.join(where_today_cm)}"
        
        today_articles = await query_db(sql_today_art, tuple(params_today_art), one=True)
        today_comments = await query_db(sql_today_cm, tuple(params_today_cm), one=True)
        today_count = (today_articles['count'] if today_articles else 0) + (today_comments['count'] if today_comments else 0)
        
        # 2. 统计周期内总数（业务关注量，使用 created_at）
        if task_where_art and task_where_art != "":
            where_total_art.append(task_where_art)
            params_total_art.extend(task_params_art)
            
        sql_total_art = f"SELECT COUNT(*) as count FROM content c WHERE {' AND '.join(where_total_art)}"
        
        if task_where_cm and task_where_cm != "":
            where_total_cm.append(task_where_cm)
            params_total_cm.extend(task_params_cm)
            
        sql_total_cm = f"SELECT COUNT(*) as count FROM comments WHERE {' AND '.join(where_total_cm)}"
        
        article_stats = await query_db(sql_total_art, tuple(params_total_art), one=True)
        comment_stats = await query_db(sql_total_cm, tuple(params_total_cm), one=True)
        
        article_count = article_stats['count'] if article_stats else 0
        comment_count = comment_stats['count'] if comment_stats else 0
        total_count = article_count + comment_count
        
        # 3. 情感分布
        # 先确保基础条件不为空
        final_where_art = " AND ".join(where_total_art) if where_total_art else "1=1"
        final_where_cm = " AND ".join(where_total_cm) if where_total_cm else "1=1"
        
        sentiment_sql = f"""
            SELECT sentiment, SUM(count) as total_count FROM (
                SELECT sentiment, COUNT(*) as count FROM content c WHERE {final_where_art} GROUP BY sentiment
                UNION ALL
                SELECT sentiment, COUNT(*) as count FROM comments WHERE {final_where_cm} GROUP BY sentiment
            ) GROUP BY sentiment
        """
        # 合并参数：文章参数在前，评论参数在后，必须与 UNION ALL 顺序一致
        all_params_sent = params_total_art + params_total_cm
        
        sentiment_dist = await query_db(sentiment_sql, tuple(all_params_sent))
        dist = {row['sentiment']: row['total_count'] for row in sentiment_dist} if sentiment_dist else {}
        
        return {
            "total": total_count,
            "articles": article_count,
            "comments": comment_count,
            "today": today_count,
            "sentiment_distribution": dist,
            "status": "success"
        }
    except Exception as e:
        print(f"Error in get_dashboard_stats: {e}")
        return {
            "total": 0, "articles": 0, "comments": 0, "today": 0,
            "sentiment_distribution": {}, "status": "partial_success", "error": str(e)
        }

@router.get("/trends")
async def get_dashboard_trends(
    days: Any = 7, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    task_id: int = None, 
    current_user: User = Depends(get_current_user)
):
    """获取过去 N 天的舆情趋势，支持任务筛选"""
    try:
        # 预处理日期参数，支持前端传来的各种日期格式
        start_date = parse_date_string(start_date)
        end_date = parse_date_string(end_date)

        # 处理自定义日期范围
        if start_date and end_date:
            if start_date == end_date:
                days = 1
            else:
                # 计算天数差异
                d1 = datetime.strptime(start_date, "%Y-%m-%d")
                d2 = datetime.strptime(end_date, "%Y-%m-%d")
                days = (d2 - d1).days + 1

        today_str = datetime.now().strftime("%Y-%m-%d")
        task_where_art, task_params_art = await build_task_filter(task_id, current_user, table_alias="c", mode="full")
        task_where_cm, task_params_cm = await build_task_filter(task_id, current_user, mode="content")

        # 归一化 days 参数为字符串以便判断
        days_str = str(days) if days is not None else "7"
        is_single_day = days_str in ["24h", "today", "yesterday", "1", "0", "-1"]

        if is_single_day:
            # 24小时趋势：获取最近24小时的数据（动态滚动窗口或指定单日）
            if start_date:
                # 如果指定了具体日期且是单日，则展示该日期的 00-23 时
                start_time = datetime.strptime(start_date, "%Y-%m-%d")
                end_time_str = start_date + " 23:59:59"
                where_art, params_art = [f"c.created_at BETWEEN ? AND ?"], [f"{start_date} 00:00:00", end_time_str]
                where_com, params_com = [f"created_at BETWEEN ? AND ?"], [f"{start_date} 00:00:00", end_time_str]
            else:
                # 使用 common.py 中的统一逻辑处理动态滚动窗口
                where_art, params_art = await build_date_filter(days, None, None, table_alias="c")
                where_com, params_com = await build_date_filter(days, None, None)
                
                # 重新计算 start_time 用于生成时间轴
                now = datetime.now()
                if days_str in ["today", "0"]:
                    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif days_str in ["yesterday", "-1"]:
                    start_time = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                else: # 24h, 1
                    start_time = now - timedelta(hours=23)
                    # 补全到小时开始
                    start_time = start_time.replace(minute=0, second=0, microsecond=0)
            
            # 任务过滤
            if task_where_art:
                where_art.append(task_where_art)
                params_art.extend(task_params_art)
            if task_where_cm:
                where_com.append(task_where_cm)
                params_com.extend(task_params_cm)
            
            # 按 YYYY-MM-DD HH 聚合，确保跨天时小时不会重叠
            sql_art = f"SELECT substr(c.created_at, 1, 13) as hour_key, sentiment, COUNT(*) as count FROM content c WHERE {' AND '.join(where_art)} GROUP BY hour_key, sentiment"
            sql_com = f"SELECT substr(created_at, 1, 13) as hour_key, sentiment, COUNT(*) as count FROM comments WHERE {' AND '.join(where_com)} GROUP BY hour_key, sentiment"
            
            art_res = await query_db(sql_art, tuple(params_art))
            com_res = await query_db(sql_com, tuple(params_com))
            
            # 生成 24 小时的时间轴序列
            hour_list = [(start_time + timedelta(hours=i)).strftime("%Y-%m-%d %H") for i in range(24)]
            data_map = {h: {"total": 0, "正面": 0, "中性": 0, "负面": 0} for h in hour_list}
            
            def process_res(res):
                for row in res:
                    hour_key = row['hour_key']
                    if hour_key in data_map:
                        sentiment = row['sentiment'] or "中性"
                        if sentiment not in ["正面", "中性", "负面"]:
                            sentiment = "中性"
                        data_map[hour_key][sentiment] += row['count']
                        data_map[hour_key]["total"] += row['count']

            if art_res: process_res(art_res)
            if com_res: process_res(com_res)
            
            results = []
            today_str = datetime.now().strftime("%Y-%m-%d")
            yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            for h_key in hour_list:
                date_part = h_key[:10]
                hour_part = h_key[11:13]
                
                # 优化 X 轴展示逻辑
                if date_part == today_str:
                    display_date = f"{hour_part}时"
                elif date_part == yesterday_str:
                    display_date = f"昨日 {hour_part}时"
                else:
                    display_date = f"{date_part[5:]} {hour_part}时" # MM-DD HH时
                
                results.append({
                    "date": display_date,
                    **data_map[h_key]
                })
            
            return results
        else:
            # 多日趋势：按日期分布
            # 确保 days 为整数以进行数学运算
            try:
                if isinstance(days, str) and days.endswith('d'):
                    days_int = int(days[:-1])
                else:
                    days_int = int(days)
            except (ValueError, TypeError):
                days_int = 7

            if start_date and end_date:
                query_start = start_date + " 00:00:00"
                query_end = end_date + " 23:59:59"
                where_art = ["c.created_at BETWEEN ? AND ?"]
                params_art = [query_start, query_end]
                where_com = ["created_at BETWEEN ? AND ?"]
                params_com = [query_start, query_end]
                
                # 重新计算实际天数
                d1 = datetime.strptime(start_date, "%Y-%m-%d")
                d2 = datetime.strptime(end_date, "%Y-%m-%d")
                days_int = (d2 - d1).days + 1
            else:
                start_date_obj = (datetime.now() - timedelta(days=days_int-1))
                query_start = start_date_obj.strftime("%Y-%m-%d") + " 00:00:00"
                where_art = ["c.created_at >= ?"]
                params_art = [query_start]
                where_com = ["created_at >= ?"]
                params_com = [query_start]
            
            if task_where_art and task_where_art != "":
                where_art.append(task_where_art)
                params_art.extend(task_params_art)
            if task_where_cm and task_where_cm != "":
                where_com.append(task_where_cm)
                params_com.extend(task_params_cm)
                
            sql_art = f"SELECT substr(c.created_at, 1, 10) as date, sentiment, COUNT(*) as count FROM content c WHERE {' AND '.join(where_art)} GROUP BY date, sentiment"
            sql_com = f"SELECT substr(created_at, 1, 10) as date, sentiment, COUNT(*) as count FROM comments WHERE {' AND '.join(where_com)} GROUP BY date, sentiment"
            
            art_res = await query_db(sql_art, tuple(params_art))
            com_res = await query_db(sql_com, tuple(params_com))
            
            # 生成日期序列
            if start_date and end_date:
                d1 = datetime.strptime(start_date, "%Y-%m-%d")
                date_list = [(d1 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_int)]
            else:
                date_list = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_int)]
                date_list.reverse()
            
            data_map = {d: {"total": 0, "正面": 0, "中性": 0, "负面": 0} for d in date_list}
            
            def process_res(res):
                for row in res:
                    date = row['date']
                    if date in data_map:
                        sentiment = row['sentiment'] or "中性"
                        if sentiment not in ["正面", "中性", "负面"]:
                            sentiment = "中性"
                        data_map[date][sentiment] += row['count']
                        data_map[date]["total"] += row['count']

            if art_res: process_res(art_res)
            if com_res: process_res(com_res)
            
            results = []
            for d in date_list:
                results.append({
                    "date": d,
                    **data_map[d]
                })
            
            return results
    except Exception as e:
        print(f"Error in get_dashboard_trends: {e}")
        return []

@router.get("/map")
async def get_dashboard_map(
    days: Any = 7, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    task_id: int = None, 
    current_user: User = Depends(get_current_user)
):
    """获取地域分布数据（基于 content 和 comments 的 ip_location 字段）"""
    try:
        where_art, params_art = await build_date_filter(days, start_date, end_date, table_alias="c")
        where_cm, params_cm = await build_date_filter(days, start_date, end_date)
        
        where_art.extend(["c.ip_location IS NOT NULL", "c.ip_location != ''"])
        where_cm.extend(["ip_location IS NOT NULL", "ip_location != ''"])

        task_where_art, task_params_art = await build_task_filter(task_id, current_user, table_alias="c", mode="full")
        task_where_cm, task_params_cm = await build_task_filter(task_id, current_user, mode="content")
        
        if task_where_art and task_where_art != "":
            where_art.append(task_where_art)
            params_art.extend(task_params_art)
            
        if task_where_cm and task_where_cm != "":
            where_cm.append(task_where_cm)
            params_cm.extend(task_params_cm)
            
        sql = f"""
            SELECT ip_location, SUM(count) as total_count FROM (
                SELECT ip_location, COUNT(*) as count FROM content c WHERE {' AND '.join(where_art)} GROUP BY ip_location
                UNION ALL
                SELECT ip_location, COUNT(*) as count FROM comments WHERE {' AND '.join(where_cm)} GROUP BY ip_location
            ) GROUP BY ip_location
        """
        res = await query_db(sql, tuple(params_art + params_cm))
        
        results = []
        if res:
            for row in res:
                loc = row['ip_location'].replace("发布于：", "").strip()
                if loc:
                    results.append({"name": loc, "value": row['total_count']})
        
        return results
    except Exception as e:
        print(f"Error in get_dashboard_map: {e}")
        return []

@router.get("/sentiment_fine")
async def get_dashboard_sentiment_fine(
    days: Any = 7, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    task_id: int = None, 
    current_user: User = Depends(get_current_user)
):
    """细粒度情感分布"""
    try:
        where_art, params_art = await build_date_filter(days, start_date, end_date, table_alias="c")
        where_cm, params_cm = await build_date_filter(days, start_date, end_date)
        
        where_art.append("c.fine_grained_sentiment IS NOT NULL")
        where_cm.append("fine_grained_sentiment IS NOT NULL")

        task_where_art, task_params_art = await build_task_filter(task_id, current_user, table_alias="c", mode="full")
        task_where_cm, task_params_cm = await build_task_filter(task_id, current_user, mode="content")
        
        if task_where_art and task_where_art != "":
            where_art.append(task_where_art)
            params_art.extend(task_params_art)
            
        if task_where_cm and task_where_cm != "":
            where_cm.append(task_where_cm)
            params_cm.extend(task_params_cm)
            
        sql_art = f"SELECT fine_grained_sentiment as sentiment, COUNT(*) as count FROM content c WHERE {' AND '.join(where_art)} GROUP BY fine_grained_sentiment"
        sql_cm = f"SELECT fine_grained_sentiment as sentiment, COUNT(*) as count FROM comments WHERE {' AND '.join(where_cm)} GROUP BY fine_grained_sentiment"
        
        sentiment_sql = f"""
            SELECT sentiment, SUM(count) as total_count FROM (
                SELECT fine_grained_sentiment as sentiment, COUNT(*) as count FROM content c WHERE {' AND '.join(where_art)} GROUP BY fine_grained_sentiment
                UNION ALL
                SELECT fine_grained_sentiment as sentiment, COUNT(*) as count FROM comments WHERE {' AND '.join(where_cm)} GROUP BY fine_grained_sentiment
            ) GROUP BY sentiment
        """
        res = await query_db(sentiment_sql, tuple(params_art + params_cm))
        
        results = [{"name": row['sentiment'], "value": row['total_count']} for row in res] if res else []
        return results
    except Exception as e:
        print(f"Error in get_dashboard_sentiment_fine: {e}")
        return []

@router.get("/intent")
async def get_dashboard_intent(
    days: Any = 7, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    task_id: int = None, 
    current_user: User = Depends(get_current_user)
):
    """意图分布"""
    try:
        where_art, params_art = await build_date_filter(days, start_date, end_date, table_alias="c")
        where_cm, params_cm = await build_date_filter(days, start_date, end_date)
        
        where_art.append("c.intent IS NOT NULL")
        where_cm.append("intent IS NOT NULL")

        task_where_art, task_params_art = await build_task_filter(task_id, current_user, table_alias="c", mode="full")
        task_where_cm, task_params_cm = await build_task_filter(task_id, current_user, mode="content")
        
        if task_where_art and task_where_art != "":
            where_art.append(task_where_art)
            params_art.extend(task_params_art)
            
        if task_where_cm and task_where_cm != "":
            where_cm.append(task_where_cm)
            params_cm.extend(task_params_cm)
            
        sql_art = f"SELECT intent, COUNT(*) as count FROM content c WHERE {' AND '.join(where_art)} GROUP BY intent"
        sql_cm = f"SELECT intent, COUNT(*) as count FROM comments WHERE {' AND '.join(where_cm)} GROUP BY intent"
        
        intent_sql = f"""
            SELECT intent, SUM(count) as total_count FROM (
                SELECT intent, COUNT(*) as count FROM content c WHERE {' AND '.join(where_art)} GROUP BY intent
                UNION ALL
                SELECT intent, COUNT(*) as count FROM comments WHERE {' AND '.join(where_cm)} GROUP BY intent
            ) GROUP BY intent
        """
        res = await query_db(intent_sql, tuple(params_art + params_cm))
        
        results = [{"name": row['intent'], "value": row['total_count']} for row in res] if res else []
        return results
    except Exception as e:
        print(f"Error in get_dashboard_intent: {e}")
        return []

@router.get("/wordcloud")
async def get_dashboard_wordcloud(
    days: Any = 7, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    task_id: int = None, 
    current_user: User = Depends(get_current_user)
):
    """关键词云（基于 content 和 comments 的 keywords 字段）"""
    try:
        where_art, params_art = await build_date_filter(days, start_date, end_date, table_alias="c")
        where_cm, params_cm = await build_date_filter(days, start_date, end_date)
        
        where_art.extend(["c.keywords IS NOT NULL", "c.keywords != ''", "c.keywords != '[]'"])
        where_cm.extend(["keywords IS NOT NULL", "keywords != ''", "keywords != '[]'"])

        task_where_art, task_params_art = await build_task_filter(task_id, current_user, table_alias="c", mode="full")
        task_where_cm, task_params_cm = await build_task_filter(task_id, current_user, mode="content")
        
        if task_where_art and task_where_art != "":
            where_art.append(task_where_art)
            params_art.extend(task_params_art)
            
        if task_where_cm and task_where_cm != "":
            where_cm.append(task_where_cm)
            params_cm.extend(task_params_cm)
            
        # 增加抽取数量，提高统计准确性
        sql_art = f"SELECT keywords FROM content c WHERE {' AND '.join(where_art)} ORDER BY created_at DESC LIMIT 2000"
        sql_cm = f"SELECT keywords FROM comments WHERE {' AND '.join(where_cm)} ORDER BY created_at DESC LIMIT 2000"
        
        art_res = await query_db(sql_art, tuple(params_art))
        com_res = await query_db(sql_cm, tuple(params_cm))
        
        # 统计总数用于估算
        count_sql_art = f"SELECT COUNT(*) as count FROM content c WHERE {' AND '.join(where_art)}"
        count_sql_cm = f"SELECT COUNT(*) as count FROM comments WHERE {' AND '.join(where_cm)}"
        total_art_res = await query_db(count_sql_art, tuple(params_art), one=True)
        total_cm_res = await query_db(count_sql_cm, tuple(params_cm), one=True)
        total_art = total_art_res['count'] if total_art_res else 0
        total_cm = total_cm_res['count'] if total_cm_res else 0
        total_total = total_art + total_cm
        
        # 解析 keywords 字段并计数
        keyword_counter = Counter()
        
        def process_keywords(res_list):
            for row in res_list:
                kw_str = row['keywords']
                if not kw_str: continue
                try:
                    kw_list = json.loads(kw_str)
                    if isinstance(kw_list, list):
                        keyword_counter.update(kw_list)
                except:
                    # 如果不是 JSON 格式，尝试按逗号/空格切分
                    kw_list = kw_str.replace(',', ' ').split()
                    keyword_counter.update([k.strip() for k in kw_list if k.strip()])

        if art_res: process_keywords(art_res)
        if com_res: process_keywords(com_res)
            
        if not keyword_counter:
            return []
            
        # 停用词列表（用于二次过滤）
        stopwords = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
            '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
            '看', '好', '自己', '这', '那', '来', '被', '与', '为', '对', '将', '从',
            '以', '及', '等', '但', '或', '而', '于', '中', '由', '可', '可以', '已',
            '已经', '还', '更', '最', '再', '因为', '所以', '如果', '虽然', '然而',
            '吧', '呢', '啊', '哦', '哈', '呀', '就是', '我们', '他们', '一个', '什么',
            '还是', '觉得', '这个', '这么', '怎么', '这种', '那个', '那个', '这么',
            '这些', '那些', '这样', '那样', '这里', '那里', '哪个', '哪些', '怎么',
            '为什么', '如何', '什么', '怎样', '可能', '可以', '应该', '必须', '能够',
            '##', '...', '....', '11', '12', '10', '20'
        }
        
        # 过滤关键词
        filtered_counts = {
            k: v for k, v in keyword_counter.items() 
            if len(k) > 1 
            and k not in stopwords 
            and not re.match(r'^[0-9]+$', k)
            and not re.match(r'^[^\w\s]+$', k)
        }
        
        top_counts = Counter(filtered_counts).most_common(100)
        
        # 估算总词频：(样本词频 / 样本记录数) * 总记录数
        sample_record_count = len(art_res) + len(com_res)
        scale_factor = total_total / sample_record_count if sample_record_count > 0 else 1
        
        results = []
        for word, count in top_counts:
            estimated_count = int(count * scale_factor)
            results.append({"name": word, "value": estimated_count})
            
        return results
    except Exception as e:
        print(f"Error in get_dashboard_wordcloud: {e}")
        return []
