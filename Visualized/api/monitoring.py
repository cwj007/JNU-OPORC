import json
import os
from urllib.parse import unquote
from collections import Counter
import jieba
import jieba.analyse
from fastapi import APIRouter, HTTPException, Body, Depends
from typing import Optional
from .database import query_db, execute_db
from .auth import get_current_user, User
from .common import PLATFORM_MAP, parse_keyword_expr

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# 图片服务器地址
IMAGE_SERVER_URL = "http://localhost:8002"

VLM_RESULT_PATH = r"e:\JNU-OPORC\Transformers\output\vlm_result.jsonl"

@router.post("/update_training_result")
async def update_training_result(
    note_id: str = Body(...),
    sentiment: str = Body(None),
    fine_grained_sentiment: str = Body(None),
    intent: str = Body(None),
    irony_detected: bool = Body(None),
    reasoning: str = Body(None),
    keywords: list = Body(None),
    ocr_text: str = Body(None),
    original_data: dict = Body(...)
):
    """
    Update article training results (sentiment, intent, reasoning, etc.)
    Sync to database and append to vlm_result.jsonl
    """
    try:
        # 1. Construct result object for jsonl
        # Filter out frontend-specific fields and restore original IDs
        result_entry = original_data.copy()
        
        # Restore original top_id if it was replaced by top_name for display
        if "original_top_id" in result_entry:
            result_entry["top_id"] = result_entry["original_top_id"]
            
        # Remove frontend-only fields
        frontend_fields = [
            "original_top_id", "is_merged_view", "is_expanded", "loading", 
            "showAllImages", "visibleImageCount", "current_comments_page", 
            "loadingComments", "sentiment_score", "relevance", "trained_keywords",
            "has_details", "matched_comment_id", "comment_content", "merge_count",
            "images", "previewIndex"
        ]
        for field in frontend_fields:
            if field in result_entry:
                del result_entry[field]
        
        # Ensure sentiment_analysis structure exists
        if "sentiment_analysis" not in result_entry or not isinstance(result_entry["sentiment_analysis"], dict):
            result_entry["sentiment_analysis"] = {}

        # Update fields in result_entry
        if sentiment is not None:
            result_entry["sentiment_analysis"]["sentiment"] = sentiment
            result_entry["sentiment"] = sentiment # Top-level sync
            # Update labels list
            result_entry["labels"] = [sentiment]
            
        if fine_grained_sentiment is not None:
            result_entry["sentiment_analysis"]["fine_grained_sentiment"] = fine_grained_sentiment
            
        if intent is not None:
            result_entry["sentiment_analysis"]["intent"] = intent
            
        if irony_detected is not None:
            result_entry["sentiment_analysis"]["irony_detected"] = irony_detected
            
        if reasoning is not None:
            result_entry["sentiment_analysis"]["reasoning"] = reasoning

        if keywords is not None:
            result_entry["keywords"] = keywords
            
        if ocr_text is not None:
            result_entry["ocr_text"] = ocr_text

        # 2. Append to vlm_result.jsonl
        os.makedirs(os.path.dirname(VLM_RESULT_PATH), exist_ok=True)
        
        with open(VLM_RESULT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(result_entry, ensure_ascii=False) + "\n")
            
        # 3. Update Database (content table only, assuming this is for articles)
        # Construct dynamic UPDATE query
        update_fields = []
        params = []
        
        if sentiment is not None:
            update_fields.append("sentiment = ?")
            params.append(sentiment)
            
        if fine_grained_sentiment is not None:
            update_fields.append("fine_grained_sentiment = ?")
            params.append(fine_grained_sentiment)
            
        if intent is not None:
            update_fields.append("intent = ?")
            params.append(intent)
            
        if irony_detected is not None:
            update_fields.append("irony_detected = ?")
            params.append(1 if irony_detected else 0) # SQLite boolean as integer
            
        if reasoning is not None:
            update_fields.append("reasoning = ?")
            params.append(reasoning)
            
        if keywords is not None:
            # Join list to string for DB storage if needed, or store as JSON string
            # Check how it's stored. Usually JSON string or comma separated.
            # Based on previous code: item["trained_keywords"] = item.get("keywords", [])
            # And query_db returns it.
            # If the DB column is TEXT, we should serialize it.
            # Let's assume JSON string for now as it's safer for lists.
            # Wait, the DB check showed 'keywords' column.
            # Let's check how it's stored in `original_data`.
            # If `original_data` has it as list, fine.
            # In DB, it's likely a string.
            update_fields.append("keywords = ?")
            params.append(json.dumps(keywords, ensure_ascii=False))
            
        if ocr_text is not None:
            update_fields.append("ocr_text = ?")
            params.append(ocr_text)

        if update_fields:
            query = f"UPDATE content SET {', '.join(update_fields)} WHERE note_id = ?"
            params.append(note_id)
            execute_db(query, tuple(params))
             
        return {"status": "success", "message": "Training result updated"}
        
    except Exception as e:
        print(f"Error updating training result: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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

@router.post("/update_comment_training_result")
async def update_comment_training_result(
    note_id: str = Body(...),
    comment_id: str = Body(...),
    sentiment: str = Body(None),
    fine_grained_sentiment: str = Body(None),
    intent: str = Body(None),
    irony_detected: bool = Body(None),
    reasoning: str = Body(None),
    keywords: list = Body(None),
    ocr_text: str = Body(None),
    original_data: dict = Body(...)
):
    """
    Update comment training results (sentiment, intent, reasoning, etc.)
    Sync to database (sentiment only) and append to vlm_result.jsonl in specific format.
    """
    try:
        # 1. Construct result object for jsonl
        c = original_data
        
        # Helper to safely get fields
        def get_val(keys, default=""):
            for k in keys:
                if k in c and c[k] is not None:
                    return c[k]
            return default

        # Ensure sentiment_analysis structure exists
        sa = c.get("sentiment_analysis", {})
        if not isinstance(sa, dict):
            sa = {}
            
        # Construct the target format
        result_entry = {
            "note_id": note_id,
            "comment_id": comment_id,
            "content": get_val(["text", "content"]),
            "image_paths": get_val(["images", "image_paths"], []),
            "source": get_val(["source"], "微博"), 
            "author": get_val(["user", "author", "user_name"]),
            "created_at": get_val(["time", "created_at"]),
            "url": get_val(["url"]),
            "ip_location": get_val(["location", "ip_location"]),
            "comment_like_count": str(get_val(["likes", "like_count", "comment_like_count"], "0")),
            "sub_comment_count": int(get_val(["reply_count", "sub_comment_count"], 0)),
            "gender": get_val(["gender"], "unknown"),
            "parent_comment_id": get_val(["parent_id", "parent_comment_id"], comment_id),
            "sentiment_analysis": sa,
            "labels": c.get("labels", []),
            "keywords": c.get("keywords", []),
            "visual_objects": c.get("visual_objects", []),
            "ocr_text": c.get("ocr_text", "")
        }
        
        # Update fields in sentiment_analysis
        if sentiment is not None:
            result_entry["sentiment_analysis"]["sentiment"] = sentiment
            # Sync top-level labels
            result_entry["labels"] = [sentiment]
            
        if fine_grained_sentiment is not None:
            result_entry["sentiment_analysis"]["fine_grained_sentiment"] = fine_grained_sentiment
            
        if intent is not None:
            result_entry["sentiment_analysis"]["intent"] = intent
            
        if irony_detected is not None:
            result_entry["sentiment_analysis"]["irony_detected"] = irony_detected
            
        if reasoning is not None:
            result_entry["sentiment_analysis"]["reasoning"] = reasoning

        if keywords is not None:
            result_entry["keywords"] = keywords
            
        if ocr_text is not None:
            result_entry["ocr_text"] = ocr_text

        # 2. Append to vlm_result.jsonl
        os.makedirs(os.path.dirname(VLM_RESULT_PATH), exist_ok=True)
        
        with open(VLM_RESULT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(result_entry, ensure_ascii=False) + "\n")
            
        # 3. Update Database (sentiment only for comments table)
        if sentiment is not None:
            execute_db("UPDATE comments SET sentiment = ? WHERE note_id = ? AND comment_id = ?", (sentiment, note_id, comment_id))
             
        return {"status": "success", "message": "Comment training result updated"}
        
    except Exception as e:
        print(f"Error updating comment result: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# --- Task Management APIs ---

@router.get("/tasks")
async def get_tasks(current_user: User = Depends(get_current_user)):
    """获取所有监控任务，并附带预警统计信息"""
    try:
        if current_user.role == 'admin':
            tasks = query_db("SELECT * FROM monitoring_tasks ORDER BY created_at DESC")
        else:
            tasks = query_db("SELECT * FROM monitoring_tasks WHERE user_id = ? ORDER BY created_at DESC", (current_user.id,))
            
        rules = query_db("SELECT * FROM alert_rules")
        
        # Build a map of rules by name for faster lookup
        rule_map = {}
        if rules:
            for r in rules:
                rule_map[r['name']] = dict(r)

        result = []
        if tasks:
            for row in tasks:
                t = dict(row)
                t["platforms"] = t["platforms"].split(",") if t["platforms"] else []
                t["notifyMethods"] = t["notify_methods"].split(",") if t.get("notify_methods") else []
                t["warningEnabled"] = bool(t["warning_enabled"])
                t["group"] = t["group_name"]
                t["warningKeywords"] = t["warning_keywords"]
                t["excludeWords"] = t["exclude_words"]
                
                # Attach advanced warning config
                rule_name = f"任务预警-{t['id']}"
                if rule_name in rule_map:
                    rule = rule_map[rule_name]
                    t["threshold"] = rule.get("threshold", 100)
                    t["is_crisis"] = rule.get("is_crisis", 0)
                    t["warning_sentiment"] = rule.get("sentiment", "负面")
                else:
                    t["threshold"] = 50 # Default to 50 as per user request example
                    t["is_crisis"] = 0
                    t["warning_sentiment"] = "负面"
                
                # Calculate warning count if enabled
                t["warning_count"] = 0
                if t["warningEnabled"]:
                    try:
                        # Construct count query
                        # Re-use logic from get_monitoring_list but simpler
                        # 1. Base constraints (Keywords, Platforms, Exclude)
                        where_clauses = []
                        params = []
                        
                        # Task Keywords
                        if t["keywords"]:
                            k_sql, k_params = parse_keyword_expr(t["keywords"], mode="full", table_alias="T")
                            if k_sql:
                                where_clauses.append(k_sql)
                                params.extend(k_params)
                        
                        # Platforms
                        if t["platforms"]:
                            platform_clauses = []
                            for p in t["platforms"]:
                                if not p.strip(): continue
                                p_str = p.strip()
                                search_terms = [p_str]
                                if p_str in PLATFORM_MAP:
                                    search_terms.append(PLATFORM_MAP[p_str])
                                or_group = []
                                for term in search_terms:
                                    or_group.append("T.source LIKE ?")
                                    params.append(f"%{term}%")
                                platform_clauses.append(f"({' OR '.join(or_group)})")
                            if platform_clauses:
                                where_clauses.append(f"({' OR '.join(platform_clauses)})")
                        
                        # Exclude Words
                        if t["excludeWords"]:
                            excludes = t["excludeWords"].replace(',', ' ').split()
                            for ew in excludes:
                                if not ew.strip(): continue
                                ew_wild = f"%{ew.strip()}%"
                                # Fix: Handle NULL top_name and lack of top_name column in content table
                                where_clauses.append("NOT (T.title LIKE ? OR T.content LIKE ? OR IFNULL(t_top.top_name, '') LIKE ?)")
                                params.extend([ew_wild, ew_wild, ew_wild])
                                
                        # Warning Keywords (The specific filter for "warning count")
                        if t["warningKeywords"]:
                            w_sql, w_params = parse_keyword_expr(t["warningKeywords"], mode="full", table_alias="T")
                            if w_sql:
                                where_clauses.append(w_sql)
                                params.extend(w_params)
                        
                        # Add Sentiment Filter (Must be Negative)
                        warning_sentiment = t.get("warning_sentiment", "负面")
                        where_clauses.append("T.sentiment = ?")
                        params.append(warning_sentiment)

                        # Build Query
                        if where_clauses:
                            # 1. Count Negative Articles
                            article_count_sql = f"""
                                SELECT COUNT(DISTINCT T.note_id) 
                                FROM content T 
                                LEFT JOIN top_topics t_top ON T.top_id = t_top.top_id
                                WHERE {' AND '.join(where_clauses)}
                            """
                            
                            # 2. Count Negative Comments
                            # Comments must match:
                            # a) Comment text matches Warning Keywords (Strictly speaking, user said "Single comment involving keywords and warning words")
                            # b) Comment sentiment is Negative
                            # c) Parent Article matches Task Keywords & Platforms (Scope)
                            # To be safe and efficient, we find comments whose parent matches scope, and the comment itself matches warning/sentiment.
                            
                            # Construct Comment Where Clauses
                            # Scope constraints (Keywords, Platforms, Exclude) apply to Parent Article (T)
                            # Warning/Sentiment constraints apply to Comment (C)
                            
                            comment_where = []
                            comment_params = []
                            
                            # Scope: Parent Article Matches
                            # We can reuse where_clauses logic but we need to separate "Scope" from "Warning"
                            # Let's rebuild carefully.
                            
                            scope_clauses = []
                            scope_params = []
                            
                            # Task Keywords (Article must match topic)
                            if t["keywords"]:
                                k_sql, k_params = parse_keyword_expr(t["keywords"], mode="full", table_alias="T")
                                if k_sql:
                                    scope_clauses.append(k_sql)
                                    scope_params.extend(k_params)
                                    
                            # Platforms (Article source)
                            if t["platforms"]:
                                platform_clauses = []
                                for p in t["platforms"]:
                                    if not p.strip(): continue
                                    p_str = p.strip()
                                    search_terms = [p_str]
                                    if p_str in PLATFORM_MAP:
                                        search_terms.append(PLATFORM_MAP[p_str])
                                    or_group = []
                                    for term in search_terms:
                                        or_group.append("T.source LIKE ?")
                                        scope_params.append(f"%{term}%")
                                    platform_clauses.append(f"({' OR '.join(or_group)})")
                                if platform_clauses:
                                    scope_clauses.append(f"({' OR '.join(platform_clauses)})")
                                    
                            # Exclude Words (Article)
                            if t["excludeWords"]:
                                excludes = t["excludeWords"].replace(',', ' ').split()
                                for ew in excludes:
                                    if not ew.strip(): continue
                                    ew_wild = f"%{ew.strip()}%"
                                    # Fix: Handle NULL top_name and lack of top_name column in content table
                                    scope_clauses.append("NOT (T.title LIKE ? OR T.content LIKE ? OR IFNULL(t_top.top_name, '') LIKE ?)")
                                    scope_params.extend([ew_wild, ew_wild, ew_wild])

                            # Comment Specific Constraints
                            comment_specific = []
                            comment_specific_params = []
                            
                            # Warning Keywords (Applied to Comment Text)
                            if t["warningKeywords"]:
                                # parse_keyword_expr generates SQL like (T.title LIKE ... OR T.content LIKE ...)
                                # We need it to apply to C.content (assuming comments table column is 'content' as seen in line 422)
                                w_sql_c, w_params_c = parse_keyword_expr(t["warningKeywords"], mode="simple", table_alias="C", column_name="content")
                                if w_sql_c:
                                    comment_specific.append(w_sql_c)
                                    comment_specific_params.extend(w_params_c)
                                    
                            # Sentiment (Applied to Comment)
                            comment_specific.append("C.sentiment = ?")
                            comment_specific_params.append(warning_sentiment)
                            
                            # Combine for Comment Query
                            # We join comments with content
                            # SELECT COUNT(DISTINCT C.comment_id) FROM comments C JOIN content T ON C.note_id = T.note_id
                            
                            full_comment_where = scope_clauses + comment_specific
                            full_comment_params = scope_params + comment_specific_params
                            
                            if full_comment_where:
                                comment_count_sql = f"""
                                    SELECT COUNT(DISTINCT C.comment_id)
                                    FROM comments C
                                    JOIN content T ON C.note_id = T.note_id
                                    LEFT JOIN top_topics t_top ON T.top_id = t_top.top_id
                                    WHERE {' AND '.join(full_comment_where)}
                                """
                                
                                # Execute Queries
                                # We need to run these against the Transformers DB
                                # query_db detects "content" or "comments" and should route correctly if logic supports it.
                                # Let's assume query_db handles it.
                                
                                article_res = query_db(article_count_sql, tuple(params), one=True)
                                article_count = article_res[0] if article_res else 0
                                
                                comment_res = query_db(comment_count_sql, tuple(full_comment_params), one=True)
                                comment_count = comment_res[0] if comment_res else 0
                                
                                t["warning_count"] = article_count + comment_count
                            else:
                                t["warning_count"] = 0
                        else:
                            t["warning_count"] = 0
                    except Exception as e:
                        print(f"Error calculating warning count for task {t['id']}: {e}")
                        t["warning_count"] = 0

                result.append(t)
        return result
    except Exception as e:
        print(f"Error getting tasks: {e}")
        return []

@router.post("/tasks")
async def create_task(task: dict = Body(...), current_user: User = Depends(get_current_user)):
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
        
        # Extra fields for alert_rules
        threshold = task.get("threshold", 50)
        is_crisis = 1 if task.get("is_crisis") else 0
        
        task_id = task.get("id")

        if task_id:
            # Check permission
            existing = query_db("SELECT user_id FROM monitoring_tasks WHERE id = ?", (task_id,), one=True)
            if existing:
                # Allow if owner or admin
                if existing['user_id'] != current_user.id and current_user.role != 'admin':
                    raise HTTPException(status_code=403, detail="Not authorized to update this task")
            
            # Update Task
            sql = """
                UPDATE monitoring_tasks 
                SET name=?, group_name=?, keywords=?, exclude_words=?, platforms=?, 
                    warning_enabled=?, warning_keywords=?, notify_methods=?, frequency=?
                WHERE id=?
            """
            execute_db(sql, (name, group, keywords, exclude_words, platforms, warning_enabled, warning_keywords, notify_methods, frequency, task_id))
        else:
            # Create Task
            sql = """
                INSERT INTO monitoring_tasks (name, group_name, keywords, exclude_words, platforms, warning_enabled, warning_keywords, notify_methods, frequency, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            # execute_db returns True/False, not ID directly with current impl, 
            # but we need ID for alert_rules.
            # We need to fetch the last inserted ID.
            execute_db(sql, (name, group, keywords, exclude_words, platforms, warning_enabled, warning_keywords, notify_methods, frequency, current_user.id))
            # Get the new ID
            last_task = query_db("SELECT id FROM monitoring_tasks ORDER BY id DESC LIMIT 1", one=True)
            if last_task:
                task_id = last_task['id']
        
        # Update/Create Alert Rule
        if task_id:
            rule_name = f"任务预警-{task_id}"
            # Check if rule exists
            existing_rule = query_db("SELECT id, user_id FROM alert_rules WHERE name = ?", (rule_name,), one=True)
            
            if existing_rule:
                execute_db("""
                    UPDATE alert_rules 
                    SET threshold=?, is_crisis=?, notify_methods=?, is_active=?, keyword=?
                    WHERE id=?
                """, (threshold, is_crisis, notify_methods, warning_enabled, warning_keywords, existing_rule['id']))
            else:
                execute_db("""
                    INSERT INTO alert_rules (name, threshold, is_crisis, notify_methods, is_active, keyword, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (rule_name, threshold, is_crisis, notify_methods, warning_enabled, warning_keywords, current_user.id))

        return {"status": "success", "message": "Task saved", "id": task_id}
            
    except Exception as e:
        print(f"Error saving task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, current_user: User = Depends(get_current_user)):
    """删除监控任务"""
    try:
        # Check permission
        existing = query_db("SELECT user_id FROM monitoring_tasks WHERE id = ?", (task_id,), one=True)
        if existing:
            if existing['user_id'] != current_user.id and current_user.role != 'admin':
                raise HTTPException(status_code=403, detail="Not authorized to delete this task")
                
        execute_db("DELETE FROM monitoring_tasks WHERE id = ?", (task_id,))
        return {"status": "success", "message": "Task deleted"}
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error deleting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/content/{note_id}")
async def delete_content(note_id: str, current_user: User = Depends(get_current_user)):
    """删除指定的内容"""
    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Only admins can delete content")
        
    try:
        # 删除 content 表中的记录
        execute_db("DELETE FROM content WHERE note_id = ?", (note_id,))
        # 删除 comments 表中的记录
        execute_db("DELETE FROM comments WHERE note_id = ?", (note_id,))
        
        return {"status": "success", "message": "Content deleted"}
    except Exception as e:
        print(f"Error deleting content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def calculate_tfidf_relevance(item, query_tokens, comment_text="", mode="full"):
    """
    Calculate relevance score using TF-IDF based on user formula:
    Total Match = (Title Score * W1) + (Content Score * W2) + (Comment Score * W3)
    Weights depend on search mode.
    """
    if not query_tokens:
        return 0
        
    # Pre-check IDF loader once
    idf_loader = jieba.analyse.default_tfidf
    if not hasattr(idf_loader, 'idf_freq'):
         jieba.analyse.extract_tags("")

    # Helper to calculate score for a field
    def get_field_score(text):
        if not text: return 0
        try:
            # Tokenize document
            words = jieba.lcut(text)
            # Filter empty
            words = [w for w in words if w.strip()]
            if not words: return 0
            
            # Calculate TF
            word_counts = Counter(words)
            total_words = len(words)
            
            score = 0
            
            for token in query_tokens:
                if token in word_counts:
                    tf = word_counts[token] / total_words
                    idf = idf_loader.idf_freq.get(token, idf_loader.median_idf)
                    score += tf * idf
                    
            return score
        except Exception as e:
            return 0

    # 1. Define weights based on mode
    # Default weights for "full" or unknown modes
    w_title, w_content, w_comment = 0.5, 0.3, 0.2
    
    if mode == "title":
        w_title, w_content, w_comment = 1.0, 0.0, 0.0
    elif mode == "content":
        w_title, w_content, w_comment = 0.0, 1.0, 0.0
    elif mode == "comment":
        w_title, w_content, w_comment = 0.0, 0.0, 1.0

    # 2. Calculate Scores
    title_text = item.get("title") or item.get("top_name") or ""
    title_score = get_field_score(title_text) if w_title > 0 else 0
    
    content_text = item.get("content") or ""
    content_score = get_field_score(content_text) if w_content > 0 else 0
    
    comment_score = get_field_score(comment_text) if w_comment > 0 else 0
    
    # 3. Weighted Sum & Normalization
    scale_factor = 50 
    
    weighted_score = (title_score * w_title) + (content_score * w_content) + (comment_score * w_comment)
    final_score = weighted_score * scale_factor
    
    return min(int(final_score), 100)

@router.get("/list")
async def get_monitoring_list(
    page: int = 1, 
    size: int = 20, 
    sentiment: str = None, 
    keyword: str = None,
    warning_keywords: str = None,
    platforms: str = None,
    exclude_words: str = None,
    keyword_mode: str = "full",
    date_start: str = None,
    date_end: str = None,
    use_sync_date: bool = False,
    merge_query: bool = False,
    sort_by: str = "time_desc",
    current_user: User = Depends(get_current_user)
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

        # --- 权限控制：普通用户只能看到自己任务范围内的数据 ---
        user_tasks = []
        if current_user.role != 'admin':
            user_tasks = query_db("SELECT id, keywords, exclude_words, platforms, warning_keywords FROM monitoring_tasks WHERE user_id = ?", (current_user.id,))
            if not user_tasks:
                # 如果没有任何任务，直接返回空
                return {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "size": size,
                    "pages": 0
                }

        def build_user_scope_filter(alias, tasks):
            """构造用户任务范围的SQL过滤条件"""
            if not tasks:
                return "", []
            
            or_groups = []
            all_params = []
            
            for t in tasks:
                # 每个任务是一个 (Keywords AND Platforms AND Exclude) 组合
                task_clauses = []
                task_params = []
                
                # 1. Keywords
                if t['keywords']:
                    k_sql, k_params = parse_keyword_expr(t['keywords'], mode="full", table_alias=alias)
                    if k_sql:
                        task_clauses.append(k_sql)
                        task_params.extend(k_params)
                
                # 2. Platforms
                if t['platforms']:
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
                            p_or.append(f"{alias}.source LIKE ?")
                            task_params.append(f"%{term}%")
                        p_clauses.append(f"({' OR '.join(p_or)})")
                    
                    if p_clauses:
                        task_clauses.append(f"({' OR '.join(p_clauses)})")
                
                # 3. Exclude
                if t['exclude_words']:
                    excludes = t['exclude_words'].replace(',', ' ').split()
                    for ew in excludes:
                        if not ew.strip(): continue
                        ew_wild = f"%{ew.strip()}%"
                        # Use top_topics check for content table 'c'
                        if alias == "c":
                            task_clauses.append(f"NOT ({alias}.title LIKE ? OR {alias}.content LIKE ? OR EXISTS (SELECT 1 FROM top_topics tt WHERE tt.top_id = {alias}.top_id AND tt.top_name LIKE ?))")
                            task_params.extend([ew_wild, ew_wild, ew_wild])
                        else:
                            # For subquery T, top_name is already available
                            task_clauses.append(f"NOT ({alias}.title LIKE ? OR {alias}.content LIKE ? OR IFNULL({alias}.top_name, '') LIKE ?)")
                            task_params.extend([ew_wild, ew_wild, ew_wild])

                # 只有当任务有具体的约束条件时才加入（避免空任务匹配所有）
                if task_clauses:
                    or_groups.append(f"({' AND '.join(task_clauses)})")
                    all_params.extend(task_params)
            
            if not or_groups:
                return "1=0", [] # 如果没有有效任务规则，不显示任何内容
                
            final_sql = f"({' OR '.join(or_groups)})"
            return final_sql, all_params

        # 应用权限过滤到主查询 params (Alias T)
        if current_user.role != 'admin':
            scope_sql, scope_params = build_user_scope_filter("T", user_tasks)
            if scope_sql:
                where_clauses.append(scope_sql)
                params.extend(scope_params)
            else:
                 # Should theoretically catch empty tasks case above, but double check
                 if not user_tasks:
                     pass # handled above
                 else:
                     # tasks exist but produced no SQL? (e.g. empty keywords)
                     # Treat as no access
                     where_clauses.append("1=0")

        if sentiment:
            # Support multiple sentiment values (comma separated)
            s_list = sentiment.split(',')
            if len(s_list) == 1:
                where_clauses.append("sentiment = ?")
                params.append(s_list[0])
            else:
                placeholders = ','.join(['?'] * len(s_list))
                where_clauses.append(f"sentiment IN ({placeholders})")
                params.extend(s_list)
        
        if platforms:
            platform_list = platforms.split(",")
            platform_clauses = []
            for p in platform_list:
                if not p.strip(): continue
                # Match platform in source
                p_str = p.strip()
                search_terms = [p_str]
                if p_str in PLATFORM_MAP:
                    search_terms.append(PLATFORM_MAP[p_str])
                
                # Create OR group for this platform: (source LIKE '%weibo%' OR source LIKE '%微博%')
                or_group = []
                for term in search_terms:
                    or_group.append("T.source LIKE ?")
                    params.append(f"%{term}%")
                
                platform_clauses.append(f"({' OR '.join(or_group)})")
            if platform_clauses:
                where_clauses.append(f"({' OR '.join(platform_clauses)})")

        if warning_keywords:
            # Warning Keywords: Strict intersection (AND) with existing filters
            # Logic: If warning keywords are provided, only return items that match them
            # This follows the user's "If user inputs warning trigger words... Return results must be..."
            
            # Use parse_keyword_expr but with "full" mode (check title, content, comment)
            w_sql, w_params = parse_keyword_expr(warning_keywords, mode="full", table_alias="T")
            if w_sql:
                where_clauses.append(w_sql)
                params.extend(w_params)

        if keyword:
            if keyword_mode == "comment":
                # Comment mode: strict matching in comments (A&B means a single comment has A and B)
                # Use strict alias to avoid ambiguity
                inner_sql, inner_params = parse_keyword_expr(keyword, mode="content", table_alias="cm_strict")
                if inner_sql:
                    where_clauses.append(f"EXISTS (SELECT 1 FROM comments cm_strict WHERE cm_strict.note_id = T.note_id AND {inner_sql})")
                    params.extend(inner_params)
            else:
                # Normal modes (Title, Content, Full)
                k_sql, k_params = parse_keyword_expr(keyword, mode=keyword_mode, table_alias="T")
                if k_sql:
                    where_clauses.append(k_sql)
                    params.extend(k_params)

        if exclude_words:
            excludes = exclude_words.replace(',', ' ').split()
            for ew in excludes:
                if not ew.strip(): continue
                ew_wild = f"%{ew.strip()}%"
                # Fix: Use T.top_name which is defined in the subquery T
                where_clauses.append("NOT (T.title LIKE ? OR T.content LIKE ? OR IFNULL(T.top_name, '') LIKE ?)")
                params.append(ew_wild)
                params.append(ew_wild)
                params.append(ew_wild)

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
                       CASE 
                           WHEN c.source IN ('知乎', 'zhihu') THEN (SELECT title FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1)
                           ELSE IFNULL(t.top_name, (SELECT title FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1))
                       END as top_name,
                       COUNT(*) as merge_count, 
                       MAX(c.{date_col}) as latest_time,
                       'merged' as type,
                       -- 获取最新的一条内容作为摘要
                       (SELECT content FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1) as content,
                       NULL as comment_content,
                       (SELECT source FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1) as source,
                       (SELECT author FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1) as author,
                       -- 简单的情感统计：取众数或最新的
                     (SELECT sentiment FROM content c2 WHERE c2.top_id = c.top_id ORDER BY {date_col} DESC LIMIT 1) as sentiment,
                     NULL as matched_comment_id,
                     -- 聚合模式下的评论采样，用于计算匹配度
                     (SELECT group_concat(content, ' ') FROM (SELECT content FROM comments cm JOIN content ct ON cm.note_id = ct.note_id WHERE ct.top_id = c.top_id ORDER BY cm.created_at DESC LIMIT 5)) as comment_sample
              FROM content c
                LEFT JOIN top_topics t ON c.top_id = t.top_id
                WHERE (c.top_id IS NOT NULL AND c.top_id != '') OR (c.source IN ('知乎', 'zhihu'))
            """
            
            full_query = base_query
            if where_clauses:
                # 重新构建针对 content 的 where_clauses (别名 c)
                c_where_clauses = []
                c_params = []

                # --- 权限控制：Merge Query ---
                if current_user.role != 'admin':
                    c_scope_sql, c_scope_params = build_user_scope_filter("c", user_tasks)
                    if c_scope_sql:
                        c_where_clauses.append(c_scope_sql)
                        c_params.extend(c_scope_params)
                    else:
                        c_where_clauses.append("1=0")

                if sentiment:
                    s_list = sentiment.split(',')
                    if len(s_list) == 1:
                        c_where_clauses.append("c.sentiment = ?")
                        c_params.append(s_list[0])
                    else:
                        placeholders = ','.join(['?'] * len(s_list))
                        c_where_clauses.append(f"c.sentiment IN ({placeholders})")
                        c_params.extend(s_list)

                if platforms:
                    platform_list = platforms.split(",")
                    platform_clauses = []
                    for p in platform_list:
                        if not p.strip(): continue
                        p_str = p.strip()
                        search_terms = [p_str]
                        if p_str in PLATFORM_MAP:
                            search_terms.append(PLATFORM_MAP[p_str])
                            
                        or_group = []
                        for term in search_terms:
                            or_group.append("c.source LIKE ?")
                            c_params.append(f"%{term}%")
                        
                        platform_clauses.append(f"({' OR '.join(or_group)})")
                        
                    if platform_clauses:
                        c_where_clauses.append(f"({' OR '.join(platform_clauses)})")

                if warning_keywords:
                    # Warning Keywords: Strict intersection for Merged Query
                    w_sql, w_params = parse_keyword_expr(warning_keywords, mode="full", table_alias="c")
                    if w_sql:
                        c_where_clauses.append(w_sql)
                        c_params.extend(w_params)

                if keyword:
                    if keyword_mode == "comment":
                        inner_sql, inner_params = parse_keyword_expr(keyword, mode="content", table_alias="cm")
                        if inner_sql:
                            c_where_clauses.append(f"EXISTS (SELECT 1 FROM comments cm WHERE cm.note_id = c.note_id AND {inner_sql})")
                            c_params.extend(inner_params)
                    else:
                        k_sql, k_params = parse_keyword_expr(keyword, mode=keyword_mode, table_alias="c")
                        if k_sql:
                            c_where_clauses.append(k_sql)
                            c_params.extend(k_params)

                if exclude_words:
                    excludes = exclude_words.replace(',', ' ').split()
                    for ew in excludes:
                        if not ew.strip(): continue
                        ew_wild = f"%{ew.strip()}%"
                        # Fix: Handle cases where top_name might not exist or be NULL
                        # In Merge Query, top_name is defined in the SELECT clause, but for filtering 
                        # we should use the same logic as the SELECT or filter against the joined table.
                        c_where_clauses.append(f"NOT (c.title LIKE ? OR c.content LIKE ? OR (CASE WHEN c.source IN ('知乎', 'zhihu') THEN c.title ELSE IFNULL(t.top_name, '') END) LIKE ?)")
                        c_params.append(ew_wild)
                        c_params.append(ew_wild)
                        c_params.append(ew_wild)
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
            
            matched_comment_expr = "NULL"
            matched_comment_params = []
            matched_comment_parts = []
            
            # 1. Warning Keywords (Highest Priority)
            matched_comment_content_parts = []
            matched_comment_content_params = []
            
            if warning_keywords:
                 # Warning keywords are always "full" mode, check if they match in comments
                 w_inner_sql, w_inner_params = parse_keyword_expr(warning_keywords, mode="content", table_alias="cm_w")
                 if w_inner_sql:
                     # ID
                     part = f"(SELECT comment_id FROM comments cm_w WHERE cm_w.note_id = content.note_id AND {w_inner_sql} LIMIT 1)"
                     matched_comment_parts.append(part)
                     matched_comment_params.extend(w_inner_params)
                     # Content
                     part_c = f"(SELECT content FROM comments cm_w WHERE cm_w.note_id = content.note_id AND {w_inner_sql} LIMIT 1)"
                     matched_comment_content_parts.append(part_c)
                     matched_comment_content_params.extend(w_inner_params)

            # 2. Normal Keywords
            if keyword and (keyword_mode == "comment" or keyword_mode == "full"):
                 # Find the first matching comment using strict logic
                 k_inner_sql, k_inner_params = parse_keyword_expr(keyword, mode="content", table_alias="cm_k")
                 if k_inner_sql:
                     # ID
                     part = f"(SELECT comment_id FROM comments cm_k WHERE cm_k.note_id = content.note_id AND {k_inner_sql} LIMIT 1)"
                     matched_comment_parts.append(part)
                     matched_comment_params.extend(k_inner_params)
                     # Content
                     part_c = f"(SELECT content FROM comments cm_k WHERE cm_k.note_id = content.note_id AND {k_inner_sql} LIMIT 1)"
                     matched_comment_content_parts.append(part_c)
                     matched_comment_content_params.extend(k_inner_params)
            
            if matched_comment_parts:
                if len(matched_comment_parts) > 1:
                    matched_comment_expr = f"COALESCE({', '.join(matched_comment_parts)})"
                else:
                    matched_comment_expr = matched_comment_parts[0]
            
            matched_comment_content_expr = "NULL"
            if matched_comment_content_parts:
                if len(matched_comment_content_parts) > 1:
                    matched_comment_content_expr = f"COALESCE({', '.join(matched_comment_content_parts)})"
                else:
                    matched_comment_content_expr = matched_comment_content_parts[0]
            
            base_query = f"""
                SELECT note_id, NULL as comment_id, title, content, NULL as comment_content, author, source, url, created_at, sync_date, sync_time, ip_location, 
                       sentiment, fine_grained_sentiment, intent, keywords, visual_objects, ocr_text, 
                       liked_count, comments_count, shared_count, 'article' as type,
                       top_id,
                       CASE 
                           WHEN source IN ('知乎', 'zhihu') THEN title 
                           ELSE (SELECT top_name FROM top_topics WHERE top_id = content.top_id) 
                       END as top_name,
                       {matched_comment_expr} as matched_comment_id,
                       {matched_comment_content_expr} as matched_comment_content,
                       (SELECT group_concat(content, ' ') FROM (SELECT content FROM comments WHERE note_id = content.note_id ORDER BY created_at DESC LIMIT 5)) as comment_sample
                FROM content
            """
            
            full_query = f"SELECT * FROM ({base_query}) AS T WHERE 1=1"
            
            # Prepend matched_comment_params and content params to params
            params = matched_comment_params + matched_comment_content_params + params
            if where_clauses:
                full_query += " AND " + " AND ".join(where_clauses)
                
            count_query = f"SELECT COUNT(*) FROM ({base_query}) AS T WHERE 1=1"
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
            elif sort_by.startswith("relevance"):
                # Relevance sort is handled in Python after fetching
                # We need all items to calculate score and sort
                pass
            else:
                # Default desc
                if use_sync_date:
                    full_query += f" ORDER BY sync_date DESC, sync_time DESC, created_at DESC"
                else:
                    full_query += f" ORDER BY created_at DESC"
        
        # 分页
        # If sorting by relevance, we must fetch all items first
        is_relevance_sort = sort_by and sort_by.startswith("relevance")
        
        if size != -1 and not is_relevance_sort:
            full_query += " LIMIT ? OFFSET ?"
            params_with_limit = params + [size, (page - 1) * size]
        else:
            params_with_limit = params

        items = query_db(full_query, tuple(params_with_limit))
        total_res = query_db(count_query, tuple(params), one=True)
        # Fix KeyError: 0 when total_res is a dict (from query_db with one=True)
        total_count = 0
        if total_res:
            if 'total' in total_res:
                total_count = total_res['total']
            else:
                # Fallback to the first value in the dict
                total_count = list(total_res.values())[0] if total_res else 0
        
        # Pre-compute query tokens for relevance scoring
        query_tokens = []
        if keyword:
            try:
                query_tokens = jieba.lcut(keyword)
                query_tokens = [t.strip() for t in query_tokens if t.strip()]
            except:
                query_tokens = []

        formatted_items = []
        if items:
            # First pass: Format items and calculate relevance
            temp_items = []
            for row in items:
                item = dict(row)
                
                if merge_query:
                    # 适配聚合结果
                    display_name = item["top_name"]
                    if display_name:
                        try:
                            display_name = unquote(display_name)
                        except:
                            pass

                    processed_item = {
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
                        "visual_objects": [],
                        "comment_sample": item.get("comment_sample", "")
                    }
                else:
                    # 普通结果
                    processed_item = item
                    try:
                        processed_item["keywords"] = json.loads(item["keywords"]) if item["keywords"] else []
                        processed_item["visual_objects"] = json.loads(item["visual_objects"]) if item["visual_objects"] else []
                    except:
                        processed_item["keywords"] = []
                        processed_item["visual_objects"] = []
                    
                    processed_item["sentiment_analysis"] = {
                        "sentiment": item.get("sentiment"),
                        "fine_grained_sentiment": item.get("fine_grained_sentiment"),
                        "intent": item.get("intent")
                    }
                    processed_item["trained_keywords"] = processed_item["keywords"]

                    # --- 新增：解码 top_name 并适配前端显示 ---
                    if item.get("top_name"):
                        try:
                            decoded = unquote(item["top_name"])
                            processed_item["top_name"] = decoded
                            processed_item["original_top_id"] = item["top_id"]
                            processed_item["top_id"] = decoded
                        except:
                            pass

                    # --- 新增：计算情感分布（文章 + 评论） ---
                    try:
                        sentiment_stats = query_db(
                            "SELECT sentiment, COUNT(*) as count FROM comments WHERE note_id = ? GROUP BY sentiment", 
                            (item["note_id"],)
                        )
                        counts = {}
                        def normalize_sentiment(s):
                            if not s or s == "Unknown": return None
                            if s in ["愤怒", "悲伤", "恐惧"]: return "负面"
                            if s in ["愉快", "喜爱"]: return "正面"
                            return s

                        article_sentiment = normalize_sentiment(item.get("sentiment"))
                        if article_sentiment:
                            counts[article_sentiment] = counts.get(article_sentiment, 0) + 1
                        if sentiment_stats:
                            for stat in sentiment_stats:
                                s_label = normalize_sentiment(stat["sentiment"])
                                s_count = stat["count"]
                                if s_label:
                                    counts[s_label] = counts.get(s_label, 0) + s_count
                        
                        total_s = sum(counts.values())
                        if total_s > 0:
                            max_s = max(counts.items(), key=lambda x: x[1])
                            processed_item["sentiment"] = max_s[0]
                            score = int((max_s[1] / total_s) * 100)
                            processed_item["sentiment_score"] = score if score > 0 else 0
                        else:
                            processed_item["sentiment"] = "中性"
                            processed_item["sentiment_score"] = 0
                    except Exception as e:
                        processed_item["sentiment_score"] = 0

                # --- 公用处理：清洗时间格式和计算匹配度 ---
                if processed_item.get("created_at"):
                    try:
                        time_str = str(processed_item["created_at"])
                        if "+" in time_str:
                            time_str = time_str.split("+")[0]
                        time_str = time_str.replace("T", " ")
                        if "." in time_str:
                            time_str = time_str.split(".")[0]
                        processed_item["created_at"] = time_str
                    except:
                        pass

                relevance_score = 0
                if keyword:
                    if merge_query:
                        comment_text = processed_item.get("comment_sample") or ""
                        relevance_score = calculate_tfidf_relevance(processed_item, query_tokens, comment_text, mode=keyword_mode)
                    else:
                        comment_text = item.get("matched_comment_content") or item.get("comment_sample") or ""
                        relevance_score = calculate_tfidf_relevance(processed_item, query_tokens, comment_text, mode=keyword_mode)
                
                processed_item["relevance"] = relevance_score
                formatted_items.append(processed_item)

        # Sort by relevance if needed
        if is_relevance_sort:
            print(f"DEBUG: Sorting by relevance, order={sort_by}")
            # Determine sort order
            reverse = True
            if sort_by == 'relevance_asc':
                reverse = False
            
            # Sort in place
            formatted_items.sort(key=lambda x: x.get("relevance", 0), reverse=reverse)
            print(f"DEBUG: Top relevance scores: {[x.get('relevance', 0) for x in formatted_items[:5]]}")
            
            # Apply pagination
            if size != -1:
                start = (page - 1) * size
                end = start + size
                formatted_items = formatted_items[start:end]

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
        # 优先直接匹配 content 表的 top_id
        check_query = "SELECT COUNT(*) FROM content WHERE top_id = ?"
        count_res = query_db(check_query, (target_top_id,), one=True)
        count = list(count_res.values())[0] if count_res else 0
        
        real_top_id = target_top_id
        is_zhihu_title = False
        
        if count == 0:
            # 尝试加上 # (对于微博话题)
            if not target_top_id.startswith("#"):
                hashed_id = f"#{target_top_id}#"
                hashed_res = query_db(check_query, (hashed_id,), one=True)
                if hashed_res and list(hashed_res.values())[0] > 0:
                    real_top_id = hashed_id
                    count = list(hashed_res.values())[0]
            
            # 尝试查 top_topics (通过名称找 ID)
            if count == 0:
                top_row = query_db("SELECT top_id FROM top_topics WHERE top_name = ?", (target_top_id,), one=True)
                if top_row:
                    real_top_id = top_row["top_id"]
                    real_res = query_db(check_query, (real_top_id,), one=True)
                    count = list(real_res.values())[0] if real_res else 0
            
            # 针对知乎：如果还是没找到，尝试作为 title 匹配
            if count == 0:
                zhihu_check = "SELECT COUNT(*) FROM content WHERE title = ? AND source IN ('知乎', 'zhihu')"
                zhihu_res = query_db(zhihu_check, (target_top_id,), one=True)
                if zhihu_res and list(zhihu_res.values())[0] > 0:
                    count = list(zhihu_res.values())[0]
                    is_zhihu_title = True

        # 3. 执行分页查询
        if is_zhihu_title:
            query = """
                SELECT * FROM content 
                WHERE title = ? AND source IN ('知乎', 'zhihu')
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
        else:
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
                    "intent": item.get("intent"),
                    "irony_detected": item.get("irony_detected"),
                    "reasoning": item.get("reasoning")
                }
                item["trained_keywords"] = item["keywords"]
                item["ocr_text"] = item.get("ocr_text", "")
                formatted_items.append(item)
                
        return formatted_items
        
    except Exception as e:
        print(f"Error in get_topic_detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detail/{note_id}")
@router.get("/detail/{note_id}/{comment_id}")
async def get_item_detail(
    note_id: str, 
    comment_id: Optional[str] = None, 
    comments_page: int = 1, 
    comments_size: int = 20,
    sentiment: Optional[str] = None
):
    """从数据库获取舆情详情，包含文章内容和相关评论(分页)"""
    try:
        # 清理 note_id
        note_id = note_id.strip()
        offset = (comments_page - 1) * comments_size
        
        # 1. 获取文章详情 (从 content 表)
        # 关联 top_topics 表以获取可读的 top_name
        # 优化：针对知乎数据增加 top_name 回退逻辑
        article_query = """
            SELECT c.*, 
                   CASE 
                       WHEN c.source IN ('知乎', 'zhihu') THEN c.title
                       ELSE IFNULL(t.top_name, c.title)
                   END as top_name,
                   'article' as type 
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
            "intent": item.get("intent"),
            "irony_detected": item.get("irony_detected"),
            "reasoning": item.get("reasoning")
        }
        item["trained_keywords"] = item["keywords"]
        item["ocr_text"] = item.get("ocr_text", "")

        # 5. 获取相关评论 (从 comments 表) - 分页
        # 如果指定了 comment_id，需要计算它在第几页
        if comment_id and comment_id != "0":
            try:
                # 假设按时间倒序
                position_query = "SELECT COUNT(*) FROM comments WHERE note_id = ? AND created_at >= (SELECT created_at FROM comments WHERE comment_id = ?)"
                position_res = query_db(position_query, (note_id, comment_id), one=True)
                position = 0
                if position_res:
                    position = list(position_res.values())[0]
                
                if position > 0:
                    comments_page = (position - 1) // comments_size + 1
                    offset = (comments_page - 1) * comments_size
            except Exception as e:
                print(f"Error calculating page for comment {comment_id}: {e}")

        # 先获取总数
        count_sql = "SELECT COUNT(*) FROM comments WHERE note_id = ?"
        count_params = [note_id]
        if sentiment:
            count_sql += " AND sentiment = ?"
            count_params.append(sentiment)
            
        count_res = query_db(count_sql, tuple(count_params), one=True)
        total_comments = list(count_res.values())[0] if count_res else 0
        item["total_comments"] = total_comments
        
        comments_sql = "SELECT * FROM comments WHERE note_id = ?"
        comments_params = [note_id]
        if sentiment:
            comments_sql += " AND sentiment = ?"
            comments_params.append(sentiment)
            
        comments_sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        comments_params.extend([comments_size, offset])
        
        comments_rows = query_db(comments_sql, tuple(comments_params))
        
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

                # 解析 JSON 字段
                c_keywords = []
                try:
                    if c_item.get("keywords"):
                        c_keywords = json.loads(c_item["keywords"]) if isinstance(c_item["keywords"], str) else c_item["keywords"]
                except: pass

                c_labels = []
                try:
                    if c_item.get("labels"):
                        c_labels = json.loads(c_item["labels"]) if isinstance(c_item["labels"], str) else c_item["labels"]
                except: pass

                c_visual_objects = []
                try:
                    if c_item.get("visual_objects"):
                        c_visual_objects = json.loads(c_item["visual_objects"]) if isinstance(c_item["visual_objects"], str) else c_item["visual_objects"]
                except: pass

                # 构造情感分析对象
                c_sentiment_analysis = {
                    "fine_grained_sentiment": c_item.get("fine_grained_sentiment"),
                    "intent": c_item.get("intent"),
                    "irony_detected": bool(c_item.get("irony_detected")) if c_item.get("irony_detected") is not None else False,
                    "reasoning": c_item.get("reasoning")
                }

                # 检查是否有分析结果
                # has_analysis = any(v is not None for v in c_sentiment_analysis.values())
                # 只要有reasoning或者intent等，就显示。哪怕只是初始化了结构。
                # 前端 v-if="comment.sentiment_analysis"
                
                item["comments"].append({
                    "id": c_item.get("comment_id"),
                    "user": c_item.get("author"),
                    "text": c_item.get("content"),
                    "sentiment": c_item.get("sentiment"),
                    "time": c_item.get("created_at"),
                    "images": c_images,
                    # 标记当前请求的评论 (如果有)
                    "is_current": str(c_item.get("comment_id")) == str(comment_id),
                    "parent_comment_id": c_item.get("parent_comment_id"),
                    # 新增字段
                    "sentiment_analysis": c_sentiment_analysis,
                    "keywords": c_keywords,
                    "labels": c_labels,
                    "visual_objects": c_visual_objects,
                    "ocr_text": c_item.get("ocr_text", "")
                })

        # 6. 补充前端需要的字段
        article_keywords = item.get("keywords", [])
        if isinstance(article_keywords, str):
            try:
                article_keywords = json.loads(article_keywords)
            except:
                article_keywords = []
        
        # 聚合所有评论的关键词
        all_comment_keywords = []
        try:
            # Query ALL keywords for this article's comments (not just the paginated ones)
            # Fetch raw JSON strings
            kw_rows = query_db("SELECT keywords FROM comments WHERE note_id = ?", (note_id,))
            if kw_rows:
                for row in kw_rows:
                    kw_json = row["keywords"]
                    if kw_json:
                        try:
                            kws = json.loads(kw_json)
                            if isinstance(kws, list):
                                all_comment_keywords.extend(kws)
                        except:
                            pass
        except Exception as e:
            print(f"Error aggregating comment keywords: {e}")

        # Calculate frequency for comment keywords
        keyword_counts = Counter(all_comment_keywords)
        # Top 20 most frequent comment keywords
        top_comment_keywords = [k for k, v in keyword_counts.most_common(20)]

        # trained_keywords: Union of Article Keywords + All Comment Keywords (Unique)
        # Use a set to remove duplicates, but preserve order if possible (article first, then high freq comments)
        unique_keywords = set(article_keywords)
        final_trained_keywords = list(article_keywords)
        
        # Append comment keywords that are not in article keywords, sorted by frequency
        for k, v in keyword_counts.most_common():
            if k not in unique_keywords:
                final_trained_keywords.append(k)
                unique_keywords.add(k)

        item["trained_keywords"] = final_trained_keywords
        item["comment_keywords"] = top_comment_keywords
        item["current_comments_page"] = comments_page # Return current page
        
        # 7. Get sentiment statistics for all comments (for accurate progress bar)
        try:
            sentiment_stats = query_db(
                "SELECT sentiment, COUNT(*) as count FROM comments WHERE note_id = ? GROUP BY sentiment", 
                (note_id,)
            )
            item["comment_sentiment_stats"] = {}
            if sentiment_stats:
                for stat in sentiment_stats:
                    s = stat["sentiment"]
                    if s:
                        item["comment_sentiment_stats"][s] = stat["count"]
        except Exception as e:
            print(f"Error getting sentiment stats: {e}")
            item["comment_sentiment_stats"] = {}

        return item

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error in get_item_detail: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
