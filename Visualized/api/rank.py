from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
import httpx
from .database import query_db
from datetime import datetime, timedelta
import json
import math
import hashlib
import re
import anyio

# 创建全局 AsyncClient 提高性能
_client = None

async def get_client():
    global _client
    if _client is None or _client.is_closed:
        # 使用适当的超时和连接池配置
        _client = httpx.AsyncClient(
            timeout=10,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
    return _client

async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None

def parse_chinese_number(num_str):
    """
    解析包含中文单位的数字字符串
    例如: "1.4亿" -> 140000000, "103.6万" -> 1036000, "2,270,719,205" -> 2270719205
    """
    if num_str is None:
        return 0
    if isinstance(num_str, (int, float)):
        return int(num_str)
        
    s = str(num_str).strip().replace(',', '')
    if not s:
        return 0
        
    try:
        if '亿' in s:
            return int(float(s.replace('亿', '')) * 100000000)
        elif '万' in s:
            return int(float(s.replace('万', '')) * 10000)
        else:
            return int(float(s))
    except ValueError:
        return 0

router = APIRouter(prefix="/rank", tags=["rank"])

@router.get("/proxy-image")
async def proxy_image(url: str):
    """
    代理获取微博图片，绕过防盗链
    """
    if not url:
        return Response(status_code=404)
        
    try:
        # 验证 URL 安全性
        if not url.startswith(('http://', 'https://')):
            return Response(status_code=400)
            
        client = await get_client()
        
        # 针对微博图片的特殊 Referer
        headers = {
            "Referer": "https://weibo.com/"
        }
        
        # 先获取 content_type
        try:
            head_resp = await client.head(url, headers=headers)
            content_type = head_resp.headers.get("Content-Type", "image/jpeg")
        except Exception:
            content_type = "image/jpeg"

        async def stream_image():
            try:
                # 使用 client.stream 提高效率
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code != 200:
                        yield b""
                    else:
                        async for chunk in response.aiter_bytes():
                            yield chunk
            except Exception as e:
                print(f"Streaming error: {e}")

        return StreamingResponse(
            stream_image(), 
            media_type=content_type
        )
            
    except Exception as e:
        print(f"Proxy image error: {e}")
        return Response(status_code=500)

@router.get("/influencers")
async def get_influencer_rank(platform: str = "all", days: int = 7):
    """获取博主/媒体影响力排名"""
    rank_data = []
    
    # --- 1. Weibo (weibo_creator) ---
    if platform in ["all", "weibo"]:
        try:
            # Get all creators and sort in Python because SQLite might not handle '1.4亿' correctly
            sql = "SELECT * FROM weibo_creator"
            rows = await query_db(sql)
            if rows:
                print(f"DEBUG: Found {len(rows)} rows in weibo_creator")
                
                # First pass: Parse all data and find max values for normalization
                parsed_rows = []
                max_fans = 0
                max_engagement = 0
                max_log_val = 0
                
                for row in rows:
                    try:
                        likes = parse_chinese_number(row['likes_count'])
                        comments = parse_chinese_number(row['comments_count'])
                        reposts = parse_chinese_number(row['reposts_count'])
                        fans = parse_chinese_number(row['fans'])
                        
                        engagement = likes + comments + reposts
                        raw_val = fans + engagement
                        
                        if fans > max_fans: max_fans = fans
                        if engagement > max_engagement: max_engagement = engagement
                        
                        log_val = math.log10(raw_val + 1)
                        if log_val > max_log_val: max_log_val = log_val
                        
                        parsed_rows.append({
                            "row": row,
                            "fans": fans,
                            "engagement": engagement,
                            "log_val": log_val
                        })
                    except Exception as parse_e:
                        print(f"Error parsing weibo row: {parse_e}")

                # Second pass: Calculate normalized scores
                for item in parsed_rows:
                    try:
                        row = item["row"]
                        fans = item["fans"]
                        engagement = item["engagement"]
                        log_val = item["log_val"]
                        
                        # Hybrid Score Algorithm:
                        # 1. Logarithmic Part (80% weight): Ensures valid scores for all tiers
                        # 2. Linear Part (20% weight): Rewards top performers significantly
                        
                        norm_log = log_val / max_log_val if max_log_val > 0 else 0
                        norm_linear = (fans + engagement) / (max_fans + max_engagement) if (max_fans + max_engagement) > 0 else 0
                        
                        final_score = (norm_log * 80) + (norm_linear * 20)
                        influence = min(99.9, round(final_score, 1))
                        
                        rank_data.append({
                            "id": f"weibo_{row['user_id']}",
                            "name": row['nickname'],
                            "platform": "微博",
                            "followers": fans,
                            "engagement": engagement,
                            "influence": influence,
                            "sentiment": 0.5, 
                            "avatar": row['avatar'] or f"https://api.dicebear.com/7.x/avataaars/svg?seed={row['nickname']}",
                            "description": row['desc'] or "活跃于微博的自媒体作者"
                        })
                    except Exception as row_e:
                        print(f"Error processing weibo row: {row_e}")
            else:
                print("DEBUG: No rows found in weibo_creator")
        except Exception as e:
            print(f"Error fetching weibo_creator: {e}")

    # --- 2. Zhihu (zhihu_creator) ---
    if platform in ["all", "zhihu"]:
        try:
            sql = "SELECT * FROM zhihu_creator"
            rows = await query_db(sql)
            if rows:
                parsed_rows = []
                max_fans = 0
                max_engagement = 0
                max_log_val = 0

                for row in rows:
                    try:
                        voteup = parse_chinese_number(row['get_voteup_count'])
                        answer = parse_chinese_number(row['anwser_count'])
                        article = parse_chinese_number(row['article_count'])
                        fans = parse_chinese_number(row['fans'])
                        
                        engagement = voteup + answer + article
                        raw_val = fans + engagement
                        
                        if fans > max_fans: max_fans = fans
                        if engagement > max_engagement: max_engagement = engagement
                        
                        log_val = math.log10(raw_val + 1)
                        if log_val > max_log_val: max_log_val = log_val
                        
                        parsed_rows.append({
                            "row": row,
                            "fans": fans,
                            "engagement": engagement,
                            "log_val": log_val
                        })
                    except Exception as e:
                        print(f"Error parsing zhihu row: {e}")

                for item in parsed_rows:
                    row = item["row"]
                    fans = item["fans"]
                    engagement = item["engagement"]
                    log_val = item["log_val"]
                    
                    norm_log = log_val / max_log_val if max_log_val > 0 else 0
                    norm_linear = (fans + engagement) / (max_fans + max_engagement) if (max_fans + max_engagement) > 0 else 0
                    
                    final_score = (norm_log * 80) + (norm_linear * 20)
                    influence = min(99.9, round(final_score, 1))
                    
                    rank_data.append({
                        "id": f"zhihu_{row['user_id']}",
                        "name": row['user_nickname'],
                        "platform": "知乎",
                        "followers": fans,
                        "engagement": engagement,
                        "influence": influence,
                        "sentiment": 0.5, # Neutral
                        "avatar": row['user_avatar'] or f"https://api.dicebear.com/7.x/avataaars/svg?seed={row['user_nickname']}",
                        "description": f"回答:{row['anwser_count']} 文章:{row['article_count']}"
                    })
        except Exception as e:
             print(f"Error fetching zhihu_creator: {e}")

    # Sort by influence descending
    rank_data.sort(key=lambda x: x['influence'], reverse=True)
    
    return {
        "status": "success",
        "data": rank_data
    }
