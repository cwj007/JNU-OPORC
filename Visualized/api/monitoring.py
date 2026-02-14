import json
from fastapi import APIRouter, HTTPException
from .database import query_db

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

@router.get("/list")
async def get_monitoring_list(
    page: int = 1, 
    size: int = 20, 
    sentiment: str = None, 
    keyword: str = None,
    date_start: str = None,
    date_end: str = None,
    use_sync_date: bool = False
):
    """从数据库分页、筛选获取舆情列表"""
    try:
        # 根据参数决定使用 created_at 还是 sync_date 进行排序和过滤
        # 如果是 created_at，需要提取日期部分进行比较
        if use_sync_date:
            date_col = "sync_date"
        else:
            date_col = "substr(created_at, 1, 10)"
        
        base_query = f"""
            SELECT note_id, NULL as comment_id, content, author, source, url, created_at, sync_date, sync_time, ip_location, 
                   sentiment, fine_grained_sentiment, intent, keywords, visual_objects, ocr_text, 
                   liked_count, comments_count, shared_count, 'article' as type
            FROM content
            UNION ALL
            SELECT note_id, comment_id, content, author, source, NULL as url, created_at, sync_date, sync_time, ip_location, 
                   sentiment, fine_grained_sentiment, intent, keywords, visual_objects, ocr_text,
                   comment_like_count as liked_count, sub_comment_count as comments_count, 0 as shared_count, 'comment' as type
            FROM comments
        """
        
        where_clauses = []
        params = []

        if sentiment:
            where_clauses.append("sentiment = ?")
            params.append(sentiment)
        
        if keyword:
            where_clauses.append("(ocr_text LIKE ? OR keywords LIKE ? OR content LIKE ?)")
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")

        if date_start:
            where_clauses.append(f"{date_col} >= ?")
            params.append(date_start)
        
        if date_end:
            where_clauses.append(f"{date_col} <= ?")
            params.append(date_end)

        full_query = f"SELECT * FROM ({base_query}) WHERE 1=1"
        if where_clauses:
            full_query += " AND " + " AND ".join(where_clauses)
            
        count_query = f"SELECT COUNT(*) FROM ({base_query}) WHERE 1=1"
        if where_clauses:
            count_query += " AND " + " AND ".join(where_clauses)

        if use_sync_date:
            full_query += f" ORDER BY sync_date DESC, sync_time DESC, created_at DESC"
        else:
            full_query += f" ORDER BY created_at DESC"
        
        # 如果 size 为 -1，则返回全部数据
        if size != -1:
            full_query += " LIMIT ? OFFSET ?"
            params_with_limit = params + [size, (page - 1) * size]
        else:
            params_with_limit = params

        items = query_db(full_query, tuple(params_with_limit))
        total_res = query_db(count_query, tuple(params), one=True)
        total_count = total_res[0] if total_res else 0

        formatted_items = []
        if items:
            for row in items:
                item = dict(row)
                try:
                    item["keywords"] = json.loads(item["keywords"]) if item["keywords"] else []
                    item["visual_objects"] = json.loads(item["visual_objects"]) if item["visual_objects"] else []
                except:
                    item["keywords"] = []
                    item["visual_objects"] = []
                
                item["sentiment_analysis"] = {
                    "sentiment": item.get("sentiment"),
                    "fine_grained_sentiment": item.get("fine_grained_sentiment"),
                    "intent": item.get("intent")
                }
                formatted_items.append(item)

        return {
            "total": total_count,
            "items": formatted_items,
            "page": page,
            "size": size
        }
    except Exception as e:
        print(f"Error in get_monitoring_list: {e}")
        return {"total": 0, "items": [], "page": page, "size": size}

@router.get("/detail/{note_id}/{comment_id}")
async def get_item_detail(note_id: str, comment_id: str):
    """从数据库获取舆情详情"""
    try:
        # 修正：应该从 content 或 comments 中查询，而不是 processed_items
        # 先查文章
        if comment_id == "0":
            row = query_db("SELECT *, 'article' as type FROM content WHERE note_id = ?", (note_id,), one=True)
        else:
            row = query_db("SELECT *, 'comment' as type FROM comments WHERE note_id = ? AND comment_id = ?", (note_id, comment_id), one=True)
            
        if row:
            item = dict(row)
            try:
                item["keywords"] = json.loads(item["keywords"]) if item["keywords"] else []
                item["visual_objects"] = json.loads(item["visual_objects"]) if item["visual_objects"] else []
            except:
                item["keywords"] = []
                item["visual_objects"] = []
            
            item["sentiment_analysis"] = {
                "sentiment": item.get("sentiment"),
                "fine_grained_sentiment": item.get("fine_grained_sentiment"),
                "intent": item.get("intent")
            }
            return item
    except Exception as e:
        print(f"Error in get_item_detail: {e}")
        
    raise HTTPException(status_code=404, detail="Item not found")
