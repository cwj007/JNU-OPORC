import json
import os
from urllib.parse import unquote
from fastapi import APIRouter, HTTPException, Body
from .database import query_db, execute_db

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# 图片服务器地址
IMAGE_SERVER_URL = "http://localhost:8002"

VLM_RESULT_PATH = r"e:\JNU-OPORC\Transformers\output\vlm_result.jsonl"

@router.post("/update_sentiment")
async def update_sentiment(
    note_id: str = Body(...),
    comment_id: str = Body(...),
    new_sentiment: str = Body(...),
    original_data: dict = Body(...)
):
    """
    更新舆情情感，并将修改后的结果保存到 vlm_result.jsonl
    """
    try:
        # 1. 构造结果对象
        result_entry = original_data.copy()
        
        # 确保 sentiment_analysis 结构存在
        if "sentiment_analysis" not in result_entry:
            result_entry["sentiment_analysis"] = {}
        elif isinstance(result_entry["sentiment_analysis"], str):
             # 如果是字符串（比如从数据库直接取出的JSON字符串），尝试解析
             try:
                 result_entry["sentiment_analysis"] = json.loads(result_entry["sentiment_analysis"])
             except:
                 result_entry["sentiment_analysis"] = {}

        # 更新情感
        result_entry["sentiment_analysis"]["sentiment"] = new_sentiment
        # 同时更新外层的 sentiment 字段（如果有）
        result_entry["sentiment"] = new_sentiment
        
        # 更新 labels
        if "labels" in result_entry:
             # 如果 labels 是列表，替换或添加
             if isinstance(result_entry["labels"], list):
                 if new_sentiment not in result_entry["labels"]:
                     # 简单的替换逻辑：清空并添加新的，或者追加？
                     # 通常情感是互斥的（正面/负面/中性），所以重置比较合理
                     result_entry["labels"] = [new_sentiment]
        else:
            result_entry["labels"] = [new_sentiment]

        # 2. 追加到 vlm_result.jsonl
        os.makedirs(os.path.dirname(VLM_RESULT_PATH), exist_ok=True)
        
        with open(VLM_RESULT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(result_entry, ensure_ascii=False) + "\n")
            
        # 3. 更新数据库
        if comment_id == "0":
            execute_db("UPDATE content SET sentiment = ? WHERE note_id = ?", (new_sentiment, note_id))
        else:
            execute_db("UPDATE comments SET sentiment = ? WHERE note_id = ? AND comment_id = ?", (new_sentiment, note_id, comment_id))
             
        return {"status": "success", "message": "Sentiment updated"}
        
    except Exception as e:
        print(f"Error updating sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Task Management APIs ---

@router.get("/tasks")
async def get_tasks():
    """获取所有监控任务"""
    try:
        tasks = query_db("SELECT * FROM monitoring_tasks ORDER BY created_at DESC")
        result = []
        if tasks:
            for row in tasks:
                t = dict(row)
                # Convert comma-separated strings back to lists/booleans
                t["platforms"] = t["platforms"].split(",") if t["platforms"] else []
                t["notifyMethods"] = t["notify_methods"].split(",") if t.get("notify_methods") else []
                t["warningEnabled"] = bool(t["warning_enabled"])
                t["group"] = t["group_name"] # alias for frontend
                t["warningKeywords"] = t["warning_keywords"]
                t["excludeWords"] = t["exclude_words"]
                result.append(t)
        return result
    except Exception as e:
        print(f"Error getting tasks: {e}")
        return []

@router.post("/tasks")
async def create_task(task: dict = Body(...)):
    """创建或更新监控任务"""
    try:
        # Prepare data
        name = task.get("name")
        group = task.get("group")
        keywords = task.get("keywords")
        exclude_words = task.get("excludeWords", "")
        platforms = ",".join(task.get("platforms", []))
        warning_enabled = 1 if task.get("warningEnabled") else 0
        warning_keywords = task.get("warningKeywords", "")
        notify_methods = ",".join(task.get("notifyMethods", []))
        frequency = task.get("frequency", "realtime")
        
        # Check if update (if id exists)
        if "id" in task and task["id"]:
            # Update
            sql = """
                UPDATE monitoring_tasks 
                SET name=?, group_name=?, keywords=?, exclude_words=?, platforms=?, 
                    warning_enabled=?, warning_keywords=?, notify_methods=?, frequency=?
                WHERE id=?
            """
            execute_db(sql, (name, group, keywords, exclude_words, platforms, warning_enabled, warning_keywords, notify_methods, frequency, task["id"]))
            return {"status": "success", "message": "Task updated", "id": task["id"]}
        else:
            # Create
            sql = """
                INSERT INTO monitoring_tasks (name, group_name, keywords, exclude_words, platforms, warning_enabled, warning_keywords, notify_methods, frequency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            execute_db(sql, (name, group, keywords, exclude_words, platforms, warning_enabled, warning_keywords, notify_methods, frequency))
            return {"status": "success", "message": "Task created"}
            
    except Exception as e:
        print(f"Error saving task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int):
    """删除监控任务"""
    try:
        execute_db("DELETE FROM monitoring_tasks WHERE id = ?", (task_id,))
        return {"status": "success", "message": "Task deleted"}
    except Exception as e:
        print(f"Error deleting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/content/{note_id}")
async def delete_content(note_id: str):
    """删除指定的内容"""
    try:
        # 删除 content 表中的记录
        execute_db("DELETE FROM content WHERE note_id = ?", (note_id,))
        # 删除 comments 表中的记录
        execute_db("DELETE FROM comments WHERE note_id = ?", (note_id,))
        # 删除 processed_items 表中的记录
        execute_db("DELETE FROM processed_items WHERE note_id = ?", (note_id,))
        
        return {"status": "success", "message": "Content deleted"}
    except Exception as e:
        print(f"Error deleting content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def get_monitoring_list(
    page: int = 1, 
    size: int = 20, 
    sentiment: str = None, 
    keyword: str = None,
    keyword_mode: str = "full",
    date_start: str = None,
    date_end: str = None,
    use_sync_date: bool = False,
    merge_query: bool = False,
    sort_by: str = "time_desc"
):
    """从数据库分页、筛选获取舆情列表"""
    try:
        # 根据参数决定使用 created_at 还是 sync_date 进行排序和过滤
        # 为了支持精确的时间过滤，直接使用完整时间字段
        if use_sync_date:
            date_col = "sync_date || ' ' || sync_time"
        else:
            date_col = "created_at"
        
        where_clauses = []
        params = []

        if sentiment:
            where_clauses.append("sentiment = ?")
            params.append(sentiment)
        
        if keyword:
            if keyword_mode == "title":
                # 修复：content 表没有 top_id，普通查询只搜 title
                # 升级：改为搜索 标题 OR 话题(#关键词#) OR 系统提取的 keywords
                where_clauses.append("(title LIKE ? OR content LIKE ? OR keywords LIKE ?)")
                params.append(f"%{keyword}%")
                params.append(f"%#{keyword}#%") # 尝试匹配带井号的话题
                params.append(f"%{keyword}%")   # 匹配系统提取的关键词
            elif keyword_mode == "content":
                where_clauses.append("(content LIKE ?)")
                params.append(f"%{keyword}%")
            else: # full
                where_clauses.append("(ocr_text LIKE ? OR keywords LIKE ? OR content LIKE ? OR title LIKE ?)")
                params.append(f"%{keyword}%")
                params.append(f"%{keyword}%")
                params.append(f"%{keyword}%")
                params.append(f"%{keyword}%")

        if date_start:
            where_clauses.append(f"{date_col} >= ?")
            params.append(date_start)
        
        if date_end:
            where_clauses.append(f"{date_col} <= ?")
            params.append(date_end)

        if merge_query:
            # 合并查询：直接基于 content 表的 top_id 进行聚合
            # 优化：不再使用 processed_items，从而自动过滤掉只有评论无文章的话题
            base_query = f"""
                SELECT c.top_id, 
                       t.top_name,
                       COUNT(*) as merge_count, 
                       MAX(c.{date_col}) as latest_time,
                       'merged' as type,
                       -- 获取最新的一条内容作为摘要
                       (SELECT content FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1) as content,
                       NULL as comment_content,
                       (SELECT source FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1) as source,
                       (SELECT author FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1) as author,
                       -- 简单的情感统计：取众数或最新的
                       (SELECT sentiment FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1) as sentiment
                FROM content c
                LEFT JOIN top_topics t ON c.top_id = t.top_id
                WHERE c.top_id IS NOT NULL AND c.top_id != ''
            """
            
            full_query = base_query
            if where_clauses:
                # 重新构建针对 content 的 where_clauses (别名 c)
                c_where_clauses = []
                c_params = []
                if sentiment:
                    c_where_clauses.append("c.sentiment = ?")
                    c_params.append(sentiment)
                if keyword:
                    if keyword_mode == "title":
                        # 搜索 top_id 或 top_name
                        c_where_clauses.append("(c.top_id LIKE ? OR t.top_name LIKE ?)")
                        c_params.append(f"%{keyword}%")
                        c_params.append(f"%{keyword}%")
                    elif keyword_mode == "content":
                        c_where_clauses.append("(c.content LIKE ?)")
                        c_params.append(f"%{keyword}%")
                    else: # full
                        c_where_clauses.append("(c.ocr_text LIKE ? OR c.keywords LIKE ? OR c.content LIKE ? OR c.top_id LIKE ? OR t.top_name LIKE ?)")
                        c_params.append(f"%{keyword}%")
                        c_params.append(f"%{keyword}%")
                        c_params.append(f"%{keyword}%")
                        c_params.append(f"%{keyword}%")
                        c_params.append(f"%{keyword}%")
                if date_start:
                    c_where_clauses.append(f"c.{date_col} >= ?")
                    c_params.append(date_start)
                if date_end:
                    c_where_clauses.append(f"c.{date_col} <= ?")
                    c_params.append(date_end)
                
                full_query += " AND " + " AND ".join(c_where_clauses)
                params = c_params # 更新 params
            
            full_query += " GROUP BY c.top_id"
            
            count_query = f"SELECT COUNT(*) FROM ({full_query})"
            
            # 排序
            if sort_by == "time_asc":
                full_query += " ORDER BY latest_time ASC"
            else:
                full_query += " ORDER BY latest_time DESC"
            
        else:
            # 普通查询
            # Updated: Only fetch articles for the list view
            # Comments will be displayed in the detail view
            base_query = f"""
                SELECT note_id, NULL as comment_id, title, content, NULL as comment_content, author, source, url, created_at, sync_date, sync_time, ip_location, 
                       sentiment, fine_grained_sentiment, intent, keywords, visual_objects, ocr_text, 
                       liked_count, comments_count, shared_count, 'article' as type,
                       top_id,
                       (SELECT top_name FROM top_topics WHERE top_id = content.top_id) as top_name
                FROM content
            """
            
            full_query = f"SELECT * FROM ({base_query}) WHERE 1=1"
            if where_clauses:
                full_query += " AND " + " AND ".join(where_clauses)
                
            count_query = f"SELECT COUNT(*) FROM ({base_query}) WHERE 1=1"
            if where_clauses:
                count_query += " AND " + " AND ".join(where_clauses)

            if sort_by == "time_asc":
                if use_sync_date:
                    full_query += f" ORDER BY sync_date ASC, sync_time ASC, created_at ASC"
                else:
                    full_query += f" ORDER BY created_at ASC"
            elif sort_by == "time_desc":
                if use_sync_date:
                    full_query += f" ORDER BY sync_date DESC, sync_time DESC, created_at DESC"
                else:
                    full_query += f" ORDER BY created_at DESC"
            else:
                # Default desc
                if use_sync_date:
                    full_query += f" ORDER BY sync_date DESC, sync_time DESC, created_at DESC"
                else:
                    full_query += f" ORDER BY created_at DESC"
        
        # 分页
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
                
                if merge_query:
                    # 适配聚合结果
                    # --- Fix: Decode top_name if present ---
                    display_name = item["top_name"]
                    if display_name:
                        try:
                            display_name = unquote(display_name)
                        except:
                            pass

                    formatted_items.append({
                        "top_id": display_name if display_name else item["top_id"], # 优先使用 top_name
                        "original_top_id": item["top_id"],
                        "merge_count": item["merge_count"],
                        "created_at": item["latest_time"], # 显示最新时间
                        "content": item["content"],
                        "source": item["source"],
                        "author": item["author"],
                        "sentiment": item["sentiment"],
                        "sentiment_analysis": {
                            "sentiment": item["sentiment"]
                        },
                        "is_merged": True,
                        "keywords": [],
                        "visual_objects": []
                    })
                else:
                    # 普通结果
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

                    # --- 新增：解码 top_name ---
                    if item.get("top_name"):
                        try:
                            # 尝试解码，如果是URL编码的
                            decoded = unquote(item["top_name"])
                            item["top_name"] = decoded
                        except:
                            pass

                    # --- 新增：计算情感分布（文章 + 评论） ---
                    try:
                        # 1. 查询评论情感统计
                        sentiment_stats = query_db(
                            "SELECT sentiment, COUNT(*) as count FROM comments WHERE note_id = ? GROUP BY sentiment", 
                            (item["note_id"],)
                        )
                        
                        # 2. 统计总数
                        counts = {}
                        
                        # 辅助函数：标准化情感标签
                        def normalize_sentiment(s):
                            if not s or s == "Unknown": return None
                            if s in ["愤怒", "悲伤", "恐惧"]: return "负面"
                            if s in ["愉快", "喜爱"]: return "正面"
                            return s

                        # 文章本身
                        article_sentiment = normalize_sentiment(item.get("sentiment"))
                        if article_sentiment:
                            counts[article_sentiment] = counts.get(article_sentiment, 0) + 1
                            
                        # 评论统计
                        if sentiment_stats:
                            for stat in sentiment_stats:
                                s_label = normalize_sentiment(stat["sentiment"])
                                s_count = stat["count"]
                                if s_label:
                                    counts[s_label] = counts.get(s_label, 0) + s_count
                        
                        total_s = sum(counts.values())
                        
                        # 3. 找出最大占比
                        if total_s > 0:
                            # 找出数量最多的情感
                            max_s = max(counts.items(), key=lambda x: x[1])
                            item["sentiment"] = max_s[0]
                            # 修正：计算最大占比的分数
                            score = int((max_s[1] / total_s) * 100)
                            item["sentiment_score"] = score if score > 0 else 0
                        else:
                            # 如果没有有效情感数据，默认中性
                            item["sentiment"] = "中性"
                            item["sentiment_score"] = 0
                            
                    except Exception as e:
                        print(f"Error calculating sentiment stats for {item.get('note_id')}: {e}")
                        item["sentiment_score"] = 0

                    # --- 新增：清洗时间格式 ---
                    if item.get("created_at"):
                        try:
                            # 移除时区信息 +08:00 并标准化格式
                            time_str = str(item["created_at"])
                            if "+" in time_str:
                                time_str = time_str.split("+")[0]
                            time_str = time_str.replace("T", " ")
                            if "." in time_str:
                                time_str = time_str.split(".")[0]
                            item["created_at"] = time_str
                        except:
                            pass

                    # --- 新增：计算匹配度 ---
                    relevance_score = 0
                    if keyword:
                        # 简单匹配算法
                        # 标题命中：50分
                        # 内容命中：每次10分，上限50分
                        # 总分上限100
                        kw = keyword.strip()
                        if kw:
                            title = item.get("title") or ""
                            content = item.get("content") or ""
                            
                            if kw in title:
                                relevance_score += 50
                            
                            count = content.count(kw)
                            relevance_score += min(count * 10, 50)
                            
                            if relevance_score > 100: relevance_score = 100
                    
                    item["relevance"] = relevance_score

                    formatted_items.append(item)

        return {
            "total": total_count,
            "items": formatted_items,
            "page": page,
            "size": size
        }
    except Exception as e:
        print(f"Error in get_monitoring_list: {e}")
        import traceback
        traceback.print_exc()
        return {"total": 0, "items": [], "page": page, "size": size}

@router.get("/topic_detail/{top_id:path}")
async def get_topic_detail(top_id: str, page: int = 1, size: int = 10):
    """获取指定 top_id 下的所有文章列表 (分页)"""
    try:
        # 1. 解码 top_id
        from urllib.parse import unquote
        decoded_top_id = unquote(top_id)
        
        target_top_id = decoded_top_id
        offset = (page - 1) * size
        
        # 2. 确定真实的 top_id
        # 优先直接匹配 content 表
        check_query = "SELECT COUNT(*) FROM content WHERE top_id = ?"
        count = query_db(check_query, (target_top_id,), one=True)[0]
        
        real_top_id = target_top_id
        
        if count == 0:
            # 尝试加上 #
            if not target_top_id.startswith("#"):
                hashed_id = f"#{target_top_id}#"
                if query_db(check_query, (hashed_id,), one=True)[0] > 0:
                    real_top_id = hashed_id
                    count = query_db(check_query, (real_top_id,), one=True)[0]
            
            # 尝试查 top_topics
            if count == 0:
                top_row = query_db("SELECT top_id FROM top_topics WHERE top_name = ?", (target_top_id,), one=True)
                if top_row:
                    real_top_id = top_row["top_id"]
                    count = query_db(check_query, (real_top_id,), one=True)[0]

        # 3. 执行分页查询
        query = """
            SELECT * FROM content 
            WHERE top_id = ? 
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        
        items = query_db(query, (real_top_id, size, offset))
        
        formatted_items = []
        if items:
            for row in items:
                item = dict(row)
                try:
                    item["keywords"] = json.loads(item["keywords"]) if item["keywords"] else []
                    item["visual_objects"] = json.loads(item["visual_objects"]) if item.get("visual_objects") else []
                    
                    # 处理图片
                    item["images"] = []
                    if item.get("image_paths"):
                        try:
                            raw_images = json.loads(item["image_paths"])
                            for img_path in raw_images:
                                if not img_path: continue
                                img_path = img_path.replace("\\", "/")
                                if "/MediaCrawler/data/" in img_path:
                                    parts = img_path.split("/MediaCrawler/data/")
                                    if len(parts) > 1:
                                        # 使用独立图片服务器
                                        item["images"].append(f"{IMAGE_SERVER_URL}/media/" + parts[1])
                                    else:
                                        item["images"].append(img_path)
                                elif img_path.startswith("http"):
                                    item["images"].append(img_path)
                                else:
                                    # 其他本地路径也指向图片服务器
                                    item["images"].append(f"{IMAGE_SERVER_URL}/media/" + img_path.lstrip("/"))
                        except:
                            item["images"] = []
                except:
                    item["keywords"] = []
                    item["visual_objects"] = []
                    item["images"] = []
                
                # --- 新增：清洗时间格式 ---
                if item.get("created_at"):
                    try:
                        # 移除时区信息 +08:00 并标准化格式
                        time_str = str(item["created_at"])
                        if "+" in time_str:
                            time_str = time_str.split("+")[0]
                        time_str = time_str.replace("T", " ")
                        if "." in time_str:
                            time_str = time_str.split(".")[0]
                        item["created_at"] = time_str
                    except:
                        pass

                item["sentiment_analysis"] = {
                    "sentiment": item.get("sentiment"),
                    "fine_grained_sentiment": item.get("fine_grained_sentiment"),
                    "intent": item.get("intent")
                }
                formatted_items.append(item)
                
        return formatted_items
        
    except Exception as e:
        print(f"Error in get_topic_detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detail/{note_id}/{comment_id}")
async def get_item_detail(note_id: str, comment_id: str, comments_page: int = 1, comments_size: int = 20):
    """从数据库获取舆情详情，包含文章内容和相关评论(分页)"""
    try:
        # 清理 note_id
        note_id = note_id.strip()
        offset = (comments_page - 1) * comments_size
        
        # 1. 获取文章详情 (从 content 表)
        # 关联 top_topics 表以获取可读的 top_name
        article_query = """
            SELECT c.*, t.top_name, 'article' as type 
            FROM content c 
            LEFT JOIN top_topics t ON c.top_id = t.top_id
            WHERE c.note_id = ?
        """
        article_row = query_db(article_query, (note_id,), one=True)
        
        if not article_row:
            # 如果找不到文章，返回 404
            raise HTTPException(status_code=404, detail="Article not found")

        item = dict(article_row)
        # 如果有 top_name，覆盖 top_id 用于显示，或者新增字段
        if item.get("top_name"):
            item["original_top_id"] = item["top_id"]
            item["top_id"] = item["top_name"]
        
        # 2. 解析 JSON 字段
        for field in ['keywords', 'visual_objects']:
            try:
                item[field] = json.loads(item[field]) if item.get(field) else []
            except (json.JSONDecodeError, TypeError):
                item[field] = []

        # 3. 处理图片路径
        item["images"] = []
        if item.get("image_paths"):
            try:
                raw_images = json.loads(item["image_paths"])
                if isinstance(raw_images, list):
                    for img_path in raw_images:
                        if not img_path: continue
                        img_path = img_path.replace("\\", "/")
                        if "/MediaCrawler/data/" in img_path:
                            parts = img_path.split("/MediaCrawler/data/")
                            if len(parts) > 1:
                                # 使用独立图片服务器
                                item["images"].append(f"{IMAGE_SERVER_URL}/media/" + parts[1])
                            else:
                                item["images"].append(img_path)
                        elif img_path.startswith("http"):
                            item["images"].append(img_path)
                        else:
                            # 其他本地路径也指向图片服务器
                            item["images"].append(f"{IMAGE_SERVER_URL}/media/" + img_path.lstrip("/"))
            except Exception:
                item["images"] = []
        
        # 4. 构造情感分析对象
        item["sentiment_analysis"] = {
            "sentiment": item.get("sentiment"),
            "fine_grained_sentiment": item.get("fine_grained_sentiment"),
            "intent": item.get("intent")
        }

        # 5. 获取相关评论 (从 comments 表) - 分页
        # 先获取总数
        count_query = "SELECT COUNT(*) FROM comments WHERE note_id = ?"
        total_comments = query_db(count_query, (note_id,), one=True)[0]
        item["total_comments"] = total_comments
        
        comments_query = "SELECT * FROM comments WHERE note_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?"
        comments_rows = query_db(comments_query, (note_id, comments_size, offset))
        
        item["comments"] = []
        if comments_rows:
            for c_row in comments_rows:
                c_item = dict(c_row)
                
                # 处理评论图片
                c_images = []
                if c_item.get("image_paths"):
                    try:
                        raw_c_images = json.loads(c_item["image_paths"])
                        if isinstance(raw_c_images, list):
                            for img_path in raw_c_images:
                                if not img_path: continue
                                img_path = img_path.replace("\\", "/")
                                if "/MediaCrawler/data/" in img_path:
                                    parts = img_path.split("/MediaCrawler/data/")
                                    if len(parts) > 1:
                                        c_images.append(f"{IMAGE_SERVER_URL}/media/" + parts[1])
                                    else:
                                        c_images.append(img_path)
                                elif img_path.startswith("http"):
                                    c_images.append(img_path)
                                else:
                                    c_images.append(f"{IMAGE_SERVER_URL}/media/" + img_path.lstrip("/"))
                    except:
                        c_images = []

                item["comments"].append({
                    "id": c_item.get("comment_id"),
                    "user": c_item.get("author"),
                    "text": c_item.get("content"),
                    "sentiment": c_item.get("sentiment"),
                    "time": c_item.get("created_at"),
                    "images": c_images,
                    # 标记当前请求的评论 (如果有)
                    "is_current": str(c_item.get("comment_id")) == str(comment_id)
                })

        # 6. 补充前端需要的字段
        item["trained_keywords"] = item.get("keywords", [])
        item["comment_keywords"] = [] # 暂时留空
        
        return item

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error in get_item_detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
