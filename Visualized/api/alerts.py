from fastapi import APIRouter, HTTPException
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

def generate_auto_alerts():
    """使用预警引擎自动生成预警"""
    try:
        engine = AlertEngine()
        engine.run_check()
    except Exception as e:
        print(f"Error generating auto alerts: {e}")

@router.get("/list")
async def get_alerts():
    """获取预警列表"""
    # 每次请求列表时尝试生成新预警
    generate_auto_alerts()
    
    # 从数据库读取
    sql = "SELECT * FROM alerts ORDER BY time DESC LIMIT 50"
    results = query_db(sql)
    
    if not results:
        return [
            {"id": 1, "level": "high", "title": "系统启动：正在初始化监控任务...", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": "read"},
        ]
        
    return [dict(row) for row in results]

@router.post("/read/{alert_id}")
async def mark_as_read(alert_id: int):
    """标记预警为已读/已处理"""
    sql = "UPDATE alerts SET status = 'read' WHERE id = ?"
    if execute_db(sql, (alert_id,)):
        return {"status": "success"}
    return {"status": "error", "message": "Failed to update alert status"}

@router.get("/rules")
async def get_rules():
    """获取预警规则列表"""
    sql = "SELECT * FROM alert_rules ORDER BY created_at DESC"
    results = query_db(sql)
    return [dict(row) for row in results] if results else []

@router.post("/rules")
async def create_rule(rule: AlertRuleSchema):
    """创建预警规则"""
    sql = """
        INSERT INTO alert_rules (name, keyword, threshold, time_window, sentiment, is_crisis, notify_methods, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    if execute_db(sql, (rule.name, rule.keyword, rule.threshold, rule.time_window, rule.sentiment, rule.is_crisis, rule.notify_methods, rule.is_active)):
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to create rule")

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int):
    """删除预警规则"""
    sql = "DELETE FROM alert_rules WHERE id = ?"
    if execute_db(sql, (rule_id,)):
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to delete rule")

@router.get("/report")
async def get_alert_report():
    """获取预警统计报告 (可视化支持)"""
    # 1. 按级别统计
    level_sql = "SELECT level, COUNT(*) as count FROM alerts GROUP BY level"
    levels = query_db(level_sql)
    
    # 2. 最近 7 天的预警趋势
    trend_sql = """
        SELECT DATE(time) as date, COUNT(*) as count 
        FROM alerts 
        WHERE time >= date('now', '-7 days')
        GROUP BY DATE(time)
    """
    trends = query_db(trend_sql)
    
    # 3. 触发最频繁的规则类型
    type_sql = "SELECT type, COUNT(*) as count FROM alerts GROUP BY type"
    types = query_db(type_sql)
    
    return {
        "level_dist": [dict(r) for r in levels] if levels else [],
        "trend": [dict(r) for r in trends] if trends else [],
        "type_dist": [dict(r) for r in types] if types else []
    }
