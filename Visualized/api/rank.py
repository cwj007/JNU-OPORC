from fastapi import APIRouter
from .database import query_db
from datetime import datetime, timedelta
import json

router = APIRouter(prefix="/rank", tags=["rank"])

@router.get("/influencers")
async def get_influencer_rank(platform: str = "all", days: int = 7):
    """获取博主/媒体影响力排名"""
    try:
        start_date = (datetime.now() - timedelta(days=days-1)).strftime("%Y-%m-%d")
        
        # 基础 SQL
        sql = """
            SELECT 
                author,
                source as platform,
                COUNT(*) as post_count,
                SUM(liked_count) as total_likes,
                SUM(comments_count) as total_comments,
                SUM(shared_count) as total_shares,
                SUM(collected_count) as total_collects,
                AVG(CASE 
                    WHEN sentiment = '正面' THEN 1.0 
                    WHEN sentiment = '负面' THEN 0.0 
                    ELSE 0.5 
                END) as avg_sentiment
            FROM content
            WHERE substr(created_at, 1, 10) >= ?
        """
        params = [start_date]
        
        if platform != "all":
            # 映射前端平台标识到数据库中的 source
            platform_map = {
                "weibo": "weibo",
                "douyin": "douyin",
                "xhs": "xhs",
                "zhihu": "zhihu"
            }
            db_platform = platform_map.get(platform, platform)
            sql += " AND source = ?"
            params.append(db_platform)
            
        sql += " GROUP BY author, source ORDER BY (SUM(liked_count) + SUM(comments_count) * 2 + SUM(shared_count) * 3) DESC LIMIT 20"
        
        results = query_db(sql, tuple(params))
        
        rank_data = []
        if results:
            for idx, row in enumerate(results):
                # 计算互动总量
                engagement = (row['total_likes'] or 0) + (row['total_comments'] or 0) + (row['total_shares'] or 0) + (row['total_collects'] or 0)
                
                # 计算影响力指数 (0-100)
                # 简单公式：log10(engagement + 1) * 10 + post_count * 2
                import math
                influence = min(99.9, round(math.log10(engagement + 1) * 15 + (row['post_count'] or 0) * 2, 1))
                
                # 模拟粉丝数 (因为 DB 中没有)
                # 使用 author 名字的 hash 生成一个相对固定的模拟值
                import hashlib
                name_hash = int(hashlib.md5(row['author'].encode()).hexdigest(), 16)
                followers = (name_hash % 9000000) + 1000000 # 100万 - 1000万之间
                
                # 平台名称映射回前端
                platform_display_map = {
                    "weibo": "微博",
                    "douyin": "抖音",
                    "xhs": "小红书",
                    "zhihu": "知乎",
                    "bilibili": "B站"
                }
                
                rank_data.append({
                    "id": idx + 1,
                    "name": row['author'],
                    "platform": platform_display_map.get(row['platform'], row['platform']),
                    "followers": followers,
                    "engagement": engagement,
                    "influence": influence,
                    "sentiment": round(row['avg_sentiment'], 2),
                    "avatar": f"https://api.dicebear.com/7.x/avataaars/svg?seed={row['author']}", # 随机头像
                    "description": f"活跃于{platform_display_map.get(row['platform'], row['platform'])}的自媒体作者"
                })
        
        return {
            "status": "success",
            "data": rank_data
        }
    except Exception as e:
        print(f"Error in get_influencer_rank: {e}")
        return {"status": "error", "message": str(e), "data": []}
