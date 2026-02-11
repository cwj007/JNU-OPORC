import json
import math
from datetime import datetime, timedelta
from fastapi import APIRouter
from .database import query_db
from .utils import is_junk_label

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/stats")
async def get_dashboard_stats(days: int = 7):
    """获取核心指标卡片数据，支持日期范围"""
    try:
        start_date = (datetime.now() - timedelta(days=days-1)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        
        article_stats = query_db("SELECT COUNT(*) as count FROM content WHERE created_at >= ?", (start_date,), one=True)
        comment_stats = query_db("SELECT COUNT(*) as count FROM comments WHERE created_at >= ?", (start_date,), one=True)
        
        article_count = article_stats['count'] if article_stats else 0
        comment_count = comment_stats['count'] if comment_stats else 0
        total_count = article_count + comment_count
        
        today_article = query_db("SELECT COUNT(*) FROM content WHERE sync_date = ?", (today,), one=True)
        today_comment = query_db("SELECT COUNT(*) FROM comments WHERE sync_date = ?", (today,), one=True)
        today_count = (today_article[0] if today_article else 0) + (today_comment[0] if today_comment else 0)
        
        sentiment_sql = """
            SELECT sentiment, SUM(count) as total_count FROM (
                SELECT sentiment, COUNT(*) as count FROM content WHERE created_at >= ? GROUP BY sentiment
                UNION ALL
                SELECT sentiment, COUNT(*) as count FROM comments WHERE created_at >= ? GROUP BY sentiment
            ) GROUP BY sentiment
        """
        sentiment_dist = query_db(sentiment_sql, (start_date, start_date))
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
async def get_dashboard_trends(days: int = 7):
    """获取过去 N 天的舆情趋势"""
    try:
        if days == 1:
            now = datetime.now()
            start_hour_dt = now - timedelta(hours=23)
            start_hour_str = start_hour_dt.strftime("%Y-%m-%d %H")
            
            trend_sql = """
                SELECT hour_key, sentiment, SUM(count) as total_count FROM (
                    SELECT substr(created_at, 1, 13) as hour_key, sentiment, COUNT(*) as count 
                    FROM content WHERE created_at >= ? GROUP BY hour_key, sentiment
                    UNION ALL
                    SELECT substr(created_at, 1, 13) as hour_key, sentiment, COUNT(*) as count 
                    FROM comments WHERE created_at >= ? GROUP BY hour_key, sentiment
                ) GROUP BY hour_key, sentiment
            """
            all_counts = query_db(trend_sql, (f"{start_hour_str}:00:00", f"{start_hour_str}:00:00"))
            
            hour_map = {}
            if all_counts:
                for row in all_counts:
                    h_key = row['hour_key']
                    if h_key not in hour_map:
                        hour_map[h_key] = {"正面": 0, "中性": 0, "负面": 0, "total": 0}
                    hour_map[h_key][row['sentiment']] = row['total_count']
                    hour_map[h_key]["total"] += row['total_count']

            trends = []
            for i in range(23, -1, -1):
                h_dt = now - timedelta(hours=i)
                h_key = h_dt.strftime("%Y-%m-%d %H")
                display_label = h_dt.strftime("%m-%d 00时") if h_dt.hour == 0 else f"{h_dt.hour:02d}时"
                hour_data = hour_map.get(h_key, {"正面": 0, "中性": 0, "负面": 0, "total": 0})
                hour_data["date"] = display_label
                trends.append(hour_data)
            return trends
        else:
            start_date = (datetime.now() - timedelta(days=days-1)).strftime("%Y-%m-%d")
            trend_sql = """
                SELECT data_date, sentiment, SUM(count) as total_count FROM (
                    SELECT substr(created_at, 1, 10) as data_date, sentiment, COUNT(*) as count 
                    FROM content WHERE created_at >= ? GROUP BY data_date, sentiment
                    UNION ALL
                    SELECT substr(created_at, 1, 10) as data_date, sentiment, COUNT(*) as count 
                    FROM comments WHERE created_at >= ? GROUP BY data_date, sentiment
                ) GROUP BY data_date, sentiment
            """
            all_counts = query_db(trend_sql, (start_date, start_date))
            
            day_map = {}
            if all_counts:
                for row in all_counts:
                    d = row['data_date']
                    if d not in day_map:
                        day_map[d] = {"正面": 0, "中性": 0, "负面": 0, "total": 0}
                    day_map[d][row['sentiment']] = row['total_count']
                    day_map[d]["total"] += row['total_count']

            dates = []
            for i in range(days-1, -1, -1):
                dates.append((datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"))
            
            trends = []
            for d in dates:
                day_data = day_map.get(d, {"正面": 0, "中性": 0, "负面": 0, "total": 0})
                day_data["date"] = d
                trends.append(day_data)
            return trends
    except Exception as e:
        print(f"Error in get_dashboard_trends: {e}")
        return []

@router.get("/map")
async def get_dashboard_map(days: int = 7):
    """获取热点区域统计"""
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        map_sql = """
            SELECT ip_location, SUM(count) as total_count FROM (
                SELECT ip_location, COUNT(*) as count FROM content 
                WHERE created_at >= ? AND ip_location IS NOT NULL AND ip_location != ''
                GROUP BY ip_location
                UNION ALL
                SELECT ip_location, COUNT(*) as count FROM comments 
                WHERE created_at >= ? AND ip_location IS NOT NULL AND ip_location != ''
                GROUP BY ip_location
            ) GROUP BY ip_location ORDER BY total_count DESC
        """
        results = query_db(map_sql, (start_date, start_date))
        
        map_data = []
        if results:
            for row in results:
                loc_raw = str(row['ip_location']).strip()
                if is_junk_label(loc_raw): continue
                loc = loc_raw.replace("中国", "").replace("省", "").replace("市", "").strip()
                if loc:
                    map_data.append({"name": loc, "value": int(row['total_count'])})
        return map_data
    except Exception as e:
        print(f"Error in get_dashboard_map: {e}")
        return []

@router.get("/sentiment_fine")
async def get_dashboard_sentiment_fine(days: int = 7):
    """获取细粒度情感分布"""
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        sql = """
            SELECT fine_grained_sentiment, SUM(count) as total_count FROM (
                SELECT fine_grained_sentiment, COUNT(*) as count FROM content WHERE created_at >= ? GROUP BY fine_grained_sentiment
                UNION ALL
                SELECT fine_grained_sentiment, COUNT(*) as count FROM comments WHERE created_at >= ? GROUP BY fine_grained_sentiment
            ) GROUP BY fine_grained_sentiment ORDER BY total_count DESC
        """
        results = query_db(sql, (start_date, start_date))
        data = []
        if results:
            for row in results:
                label = row['fine_grained_sentiment']
                if is_junk_label(label): continue
                data.append({"name": label, "value": int(row['total_count'])})
        return data
    except Exception as e:
        print(f"Error in get_dashboard_sentiment_fine: {e}")
        return []

@router.get("/intent")
async def get_dashboard_intent(days: int = 7):
    """获取意图类别分布"""
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        sql = """
            SELECT intent, SUM(count) as total_count FROM (
                SELECT intent, COUNT(*) as count FROM content WHERE created_at >= ? GROUP BY intent
                UNION ALL
                SELECT intent, COUNT(*) as count FROM comments WHERE created_at >= ? GROUP BY intent
            ) GROUP BY intent ORDER BY total_count DESC
        """
        results = query_db(sql, (start_date, start_date))
        data = []
        if results:
            for row in results:
                label = row['intent']
                if is_junk_label(label): continue
                data.append({"name": label, "value": int(row['total_count'])})
        return data
    except Exception as e:
        print(f"Error in get_dashboard_intent: {e}")
        return []

@router.get("/wordcloud")
async def get_dashboard_wordcloud(days: int = 7):
    """获取词云数据"""
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        sql = "SELECT keywords FROM content WHERE created_at >= ? UNION ALL SELECT keywords FROM comments WHERE created_at >= ?"
        results = query_db(sql, (start_date, start_date))
        
        word_counts = {}
        if results:
            for row in results:
                if row['keywords']:
                    try:
                        keywords = json.loads(row['keywords'])
                        for k in keywords:
                            if is_junk_label(k): continue
                            word_counts[k] = word_counts.get(k, 0) + 1
                    except: continue
        
        data = [{"name": k, "value": v} for k, v in word_counts.items()]
        data.sort(key=lambda x: x['value'], reverse=True)
        return data[:100]
    except Exception as e:
        print(f"Error in get_dashboard_wordcloud: {e}")
        return []
