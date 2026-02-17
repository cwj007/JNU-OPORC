from fastapi import APIRouter, HTTPException, BackgroundTasks
from .database import query_db, execute_db, HOTSEARCH_DB_PATH
from .alert_engine import AlertEngine
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
from datetime import datetime, timedelta

router = APIRouter(prefix="/alerts", tags=["alerts"])

class AlertRuleSchema(BaseModel):
    name: str
    keyword: Optional[str] = ""
    threshold: int = 100
    time_window: int = 1
    sentiment: str = "负面"
    is_crisis: int = 0
    notify_methods: str = "system"
    is_active: int = 1
    rule_type: Optional[str] = "threshold"
    config: Optional[str] = "{}"

# 全局变量记录上次检查时间
LAST_CHECK_TIME = None

def ensure_default_rules():
    """Ensure default global CRI rule exists"""
    try:
        # Check if default rule exists
        sql = "SELECT id FROM alert_rules WHERE name = '全网负面内容监测'"
        existing = query_db(sql, one=True)
        
        if not existing:
            print("[Init] Creating default global CRI rule...")
            insert_sql = """
                INSERT INTO alert_rules (name, keyword, threshold, time_window, sentiment, is_crisis, notify_methods, is_active, rule_type, config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            execute_db(insert_sql, (
                "全网负面内容监测",
                "", # All keywords
                1,
                24, # 24h default
                "负面",
                0,
                "system",
                1,
                "cri_trend",
                "{}"
            ))
    except Exception as e:
        print(f"Error ensuring default rules: {e}")

def sync_monitor_tasks_to_rules():
    """同步监测任务到预警规则 (双向同步支持)"""
    try:
        # 1. 获取所有监测任务 (无论是否开启预警)
        tasks_sql = "SELECT * FROM monitoring_tasks"
        tasks = query_db(tasks_sql)
        tasks = tasks if tasks else []
        
        # 构建所有存在的任务规则名称集合 (用于检测已删除的任务)
        all_task_rule_names = {f"【监测任务】{task['name']}" for task in tasks}

        # 2. 获取现有“监测任务”类型的规则
        existing_rules_sql = "SELECT id, name FROM alert_rules WHERE name LIKE '【监测任务】%'"
        existing_rules = query_db(existing_rules_sql)
        existing_rules_map = {row['name']: row['id'] for row in existing_rules} if existing_rules else {}

        # 3. 同步：添加或更新规则
        for task in tasks:
            task_name = f"【监测任务】{task['name']}"
            is_active = task['warning_enabled']
            
            # 如果规则已存在，更新关键词和状态
            if task_name in existing_rules_map:
                rule_id = existing_rules_map[task_name]
                keyword = task['warning_keywords'] if task['warning_keywords'] else task['keywords']
                update_sql = "UPDATE alert_rules SET keyword = ?, is_active = ? WHERE id = ?"
                execute_db(update_sql, (keyword, is_active, rule_id))
                continue
                
            # 插入新规则 (即使未开启预警也创建规则，但设为禁用)
            keyword = task['warning_keywords'] if task['warning_keywords'] else task['keywords']
            
            sql = """
                INSERT INTO alert_rules (name, keyword, threshold, time_window, sentiment, is_crisis, notify_methods, is_active, rule_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            execute_db(sql, (
                task_name, 
                keyword, 
                1, # Threshold default 1
                24, # Time window 24h (check daily window)
                '负面', 
                0, 
                task['notify_methods'] or 'system', 
                is_active, 
                'threshold'
            ))
            print(f"[Sync] Created alert rule for task: {task['name']}")

        # 4. 同步：删除无效规则 (Task deleted -> Rule deleted)
        # 只有当任务真正从 monitoring_tasks 表中删除时，才删除对应的规则
        for rule_name, rule_id in existing_rules_map.items():
            if rule_name not in all_task_rule_names:
                print(f"[Sync] Deleting obsolete alert rule: {rule_name}")
                execute_db("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
            
    except Exception as e:
        print(f"Error syncing monitor tasks: {e}")

def generate_auto_alerts(override_days: int = None, force: bool = False):
    """使用预警引擎自动生成预警"""
    global LAST_CHECK_TIME
    
    # 确保默认规则存在
    ensure_default_rules()
    # 同步监测任务
    sync_monitor_tasks_to_rules()
    
    # 简单的节流机制：如果距离上次检查不足 5 分钟，且不是强制覆盖模式，则跳过
    # 注意：override_days 总是会被传递，所以我们需要更智能的判断
    # 这里假设如果 override_days 很大（比如默认的30），我们仍然希望有节流
    
    now = datetime.now()
    if not force and LAST_CHECK_TIME and (now - LAST_CHECK_TIME).total_seconds() < 300:
        print("[Skip Check] Throttled (checked within 5 mins)")
        return

    try:
        print(f"[Auto Alert] Running check (days={override_days})...")
        engine = AlertEngine()
        engine.run_check(override_days=override_days)
        LAST_CHECK_TIME = now
    except Exception as e:
        print(f"Error generating auto alerts: {e}")

@router.get("/list")
async def get_alerts(
    days: Optional[int] = 1, 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    level: Optional[str] = None,
    page: int = 1,
    page_size: int = 10
):
    """
    获取预警列表 (分页支持)
    - days: 预设天数 (1=24h, 3=3天, 7=7天, etc.)
    - start_date/end_date: 自定义日期范围 (YYYY-MM-DD)
    - level: 风险级别筛选 (high, medium, low, etc.)
    - page: 当前页码 (默认1)
    - page_size: 每页数量 (默认10)
    """
    # 每次请求列表时尝试生成新预警
    # 策略：
    # 1. 如果 alerts 表为空（初次运行或被清空），强制执行一次历史扫描（例如过去7天），以检测现存风险。
    # 2. 如果非空，仅当用户请求 days > 1 时扫描历史。
    # 3. 否则，仅执行规则定义的默认周期检查（避免重复）。
    
    # has_alerts = query_db("SELECT id FROM alerts LIMIT 1", one=True)
    
    # if not has_alerts:
    #     print("[Auto Alert] Alerts table empty, performing initial history scan (7 days)...")
    #     check_days = 7
    # else:
    #     check_days = days if days and days > 1 else None 
        
    # generate_auto_alerts(override_days=check_days) 
    
    # 简化逻辑：仅执行规则定义的默认周期检查（不进行强制历史扫描）
    generate_auto_alerts(override_days=None) 
    
    # 构建时间查询条件
    if start_date and end_date:
        # 自定义范围
        # 补全时间，start_date 00:00:00 到 end_date 23:59:59
        where_clause = f"time BETWEEN '{start_date} 00:00:00' AND '{end_date} 23:59:59'"
    elif days:
        # 预设天数
        time_threshold = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        where_clause = f"time >= '{time_threshold}'"
    else:
        # 默认 24h
        time_threshold = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        where_clause = f"time >= '{time_threshold}'"

    # 添加风险等级筛选
    if level and level != 'all':
        if level == 'high':
            where_clause += " AND (level = 'high' OR level = 'red')"
        elif level == 'medium':
            where_clause += " AND (level = 'medium' OR level = 'yellow')"
        elif level == 'low':
            where_clause += " AND (level = 'low' OR level = 'green')"
        else:
            where_clause += f" AND level = '{level}'"

    # 计算总数
    count_sql = f"SELECT COUNT(*) as total FROM alerts WHERE {where_clause}"
    total_res = query_db(count_sql, one=True)
    total = total_res['total'] if total_res else 0

    # 分页查询
    offset = (page - 1) * page_size
    sql = f"SELECT * FROM alerts WHERE {where_clause} ORDER BY time DESC LIMIT {page_size} OFFSET {offset}"
    results = query_db(sql)
    
    processed_results = []
    if results:
        # 解析 meta_data JSON 字符串
        for row in results:
            item = dict(row)
            if item.get("meta_data"):
                try:
                    item["meta_data"] = json.loads(item["meta_data"])
                except:
                    item["meta_data"] = {}
            else:
                item["meta_data"] = {}
            processed_results.append(item)
    else:
        # 只有在没有历史数据且查询的是默认范围时才显示提示
        if days == 1 and not start_date and page == 1:
             processed_results = [
                {"id": 1, "level": "green", "title": "暂无预警", "content": "当前时间范围内未检测到异常预警。", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": "read"},
            ]
             total = 1

    return {
        "data": processed_results,
        "total": total,
        "page": page,
        "page_size": page_size
    }

@router.post("/read/{alert_id}")
async def mark_as_read(alert_id: int):
    """标记预警为已读/已处理"""
    sql = "UPDATE alerts SET status = 'read' WHERE id = ?"
    if execute_db(sql, (alert_id,)):
        return {"status": "success"}
    return {"status": "error", "message": "Failed to update alert status"}

@router.get("/details/{reference_id}")
async def get_alert_details(reference_id: str):
    """
    Fetch full article details and negative comments.
    Priority:
    1. Check 'alerts' table in hotsearch.db (Cache)
    2. Fallback to 'Transformers/processed_ids.db' (Source)
    """
    try:
        # 1. Try to fetch from Cache (hotsearch.db -> alerts table)
        # query_db routes to HOTSEARCH_DB_PATH because table name "alerts" is in the query (implicit default)
        # or we can be explicit if needed, but "alerts" is not in the transformers list
        cache_sql = "SELECT meta_data FROM alerts WHERE reference_id = ? ORDER BY id DESC LIMIT 1"
        cached_row = query_db(cache_sql, (reference_id,), one=True)
        
        if cached_row and cached_row['meta_data']:
            try:
                import json
                meta = json.loads(cached_row['meta_data'])
                
                # Extract counts with fallbacks
                total = meta.get('total_comments', 0)
                neg_count = meta.get('negative_comments_count') or meta.get('neg_comments', 0)
                
                # Check if we have substantial data
                # If total_comments is 0, treat as soft miss and try source DB to get latest stats
                if total > 0 and meta.get('article_content') and meta.get('top_negative_comments'):
                    print(f"[Cache Hit] Returning details for {reference_id} from hotsearch.db")
                    return {
                        "title": meta.get('article_title', ''),
                        "content": meta.get('article_content', ''),
                        "publish_time": meta.get('publish_time', ''),
                        "author": meta.get('author', ''), # Might not be in meta, but content is key
                        "url": meta.get('url', ''),
                        "comments": meta.get('top_negative_comments', []),
                        "total_comments": total,
                        "negative_count": neg_count,
                        "cri": meta.get('cri'),
                        "metrics": meta.get('metrics')
                    }
                else:
                    print(f"[Cache Soft Miss] Meta has 0 comments or missing content, trying source DB for {reference_id}")
            except Exception as e:
                print(f"[Cache Error] Failed to parse meta_data: {e}")

        # 2. Fallback: Fetch from Source (Transformers/processed_ids.db)
        print(f"[Cache Miss] Fetching details for {reference_id} from Transformers DB")
        
        # query_db routes to TRANSFORMERS_DB_PATH because table name "content" is in the query
        article_sql = "SELECT * FROM content WHERE note_id = ?"
        article = query_db(article_sql, (reference_id,), one=True)
        
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        article_dict = dict(article)
        
        # Fetch all comments
        # query_db routes to TRANSFORMERS_DB_PATH because table name "comments" is in the query
        comments_sql = "SELECT * FROM comments WHERE note_id = ?"
        comments = query_db(comments_sql, (reference_id,))
        
        comments_list = [dict(c) for c in comments] if comments else []
        
        # Filter and sort negative comments
        negative_comments = []
        from .risk_assessment import get_sentiment_score, calculate_cri, determine_level, get_dynamic_threshold
        
        for c in comments_list:
            score = 0
            try:
                score = get_sentiment_score(c.get('sentiment', ''))
            except:
                pass
                
            # Filter for negative comments (sentiment='负面' or score >= 0.6)
            is_negative = (c.get('sentiment') == '负面') or (score >= 0.6)
            
            if is_negative:
                c['score'] = score
                negative_comments.append(c)
        
        # Sort by score descending
        negative_comments.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Calculate CRI on the fly for fallback
        cri, cri_details = calculate_cri(article_dict, comments_list)
        mu, sigma = get_dynamic_threshold()
        risk_level, risk_label = determine_level(cri, mu, sigma)

        return {
            "title": article_dict.get('title', ''),
            "content": article_dict.get('content', ''),
            "publish_time": article_dict.get('created_at', ''),
            "author": article_dict.get('author', ''),
            "url": article_dict.get('url', ''),
            "comments": negative_comments, # Return ALL negative comments
            "total_comments": len(comments_list),
            "negative_count": len(negative_comments),
            "cri": cri,
            "risk_level": risk_level,
            "metrics": {
                "sentiment_score": cri_details.get('a_neg', 0),
                "negative_ratio": cri_details.get('c_ratio', 0),
                "burst_coefficient": cri_details.get('burst_factor', 0)
            }
        }
        
    except Exception as e:
        print(f"Error fetching details for {reference_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rules", response_model=List[dict])
async def get_rules():
    """获取预警规则列表"""
    sql = "SELECT * FROM alert_rules ORDER BY created_at DESC"
    results = query_db(sql)
    return [dict(row) for row in results] if results else []

@router.post("/rules")
async def create_rule(rule: AlertRuleSchema, background_tasks: BackgroundTasks):
    """创建预警规则"""
    sql = """
        INSERT INTO alert_rules (name, keyword, threshold, time_window, sentiment, is_crisis, notify_methods, is_active, rule_type, config)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    if execute_db(sql, (rule.name, rule.keyword, rule.threshold, rule.time_window, rule.sentiment, rule.is_crisis, rule.notify_methods, rule.is_active, rule.rule_type, rule.config)):
        # Trigger immediate check in background
        print(f"[Manual Create] Triggering immediate check for new rule {rule.name}")
        background_tasks.add_task(generate_auto_alerts, force=True)
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to create rule")

@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, rule: AlertRuleSchema, background_tasks: BackgroundTasks):
    """更新预警规则"""
    
    # Check if it's a synced rule (Monitoring Task)
    if rule.name.startswith("【监测任务】"):
        task_name = rule.name.replace("【监测任务】", "")
        # Sync back to Monitoring Tasks: Update warning_enabled status
        print(f"[Sync] Updating warning status for task: {task_name} -> {rule.is_active}")
        update_task_sql = "UPDATE monitoring_tasks SET warning_enabled = ? WHERE name = ?"
        execute_db(update_task_sql, (rule.is_active, task_name))

    sql = """
        UPDATE alert_rules 
        SET name=?, keyword=?, threshold=?, time_window=?, sentiment=?, is_crisis=?, notify_methods=?, is_active=?, rule_type=?, config=?
        WHERE id=?
    """
    if execute_db(sql, (rule.name, rule.keyword, rule.threshold, rule.time_window, rule.sentiment, rule.is_crisis, rule.notify_methods, rule.is_active, rule.rule_type, rule.config, rule_id)):
        # Trigger immediate check in background
        print(f"[Manual Update] Triggering immediate check for updated rule {rule.name}")
        background_tasks.add_task(generate_auto_alerts, force=True)
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to update rule")

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int):
    """删除预警规则 (双向同步支持)"""
    # 1. Check if it's a synced rule
    rule_sql = "SELECT name FROM alert_rules WHERE id = ?"
    rule = query_db(rule_sql, (rule_id,), one=True)
    
    if rule and rule['name'].startswith("【监测任务】"):
        task_name = rule['name'].replace("【监测任务】", "")
        # Sync back to Monitoring Tasks: Disable warning
        print(f"[Sync] Disabling warning for task: {task_name}")
        update_sql = "UPDATE monitoring_tasks SET warning_enabled = 0 WHERE name = ?"
        execute_db(update_sql, (task_name,))

    sql = "DELETE FROM alert_rules WHERE id = ?"
    if execute_db(sql, (rule_id,)):
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to delete rule")

@router.get("/report")
async def get_alert_report(days: Optional[int] = 7, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """获取预警统计报告 (可视化支持)"""
    
    # 构建时间查询条件
    if start_date and end_date:
        time_condition = f"time BETWEEN '{start_date} 00:00:00' AND '{end_date} 23:59:59'"
    elif days:
        time_threshold = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        time_condition = f"time >= '{time_threshold}'"
    else:
        time_threshold = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        time_condition = f"time >= '{time_threshold}'"

    # 1. 按级别统计
    level_sql = f"SELECT level, COUNT(*) as count FROM alerts WHERE {time_condition} GROUP BY level"
    levels = query_db(level_sql)
    
    # 2. 预警趋势
    trend_sql = f"""
        SELECT strftime('%Y-%m-%d %H:%M', time) as date, COUNT(*) as count 
        FROM alerts 
        WHERE {time_condition}
        GROUP BY strftime('%Y-%m-%d %H:%M', time)
        ORDER BY date ASC
    """
    trends = query_db(trend_sql)
    
    # 3. 触发最频繁的规则类型
    type_sql = f"SELECT type, COUNT(*) as count FROM alerts WHERE {time_condition} GROUP BY type"
    types = query_db(type_sql)
    
    return {
        "level_dist": [dict(r) for r in levels] if levels else [],
        "trend": [dict(r) for r in trends] if trends else [],
        "type_dist": [dict(r) for r in types] if types else []
    }
