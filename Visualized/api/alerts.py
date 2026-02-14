from fastapi import APIRouter
from .database import query_db, HOTSEARCH_DB_PATH
import sqlite3
from datetime import datetime, timedelta

router = APIRouter(prefix="/alerts", tags=["alerts"])

def generate_auto_alerts():
    """根据最新舆情数据自动生成预警"""
    try:
        # 1. 检查最近 24 小时的负面舆情
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        negative_sql = "SELECT COUNT(*) as count FROM content WHERE sentiment = '负面' AND created_at >= ?"
        neg_count_row = query_db(negative_sql, (yesterday,), one=True)
        neg_count = neg_count_row['count'] if neg_count_row else 0
        
        new_alerts = []
        if neg_count > 5:
            new_alerts.append({
                "level": "high",
                "title": f"负面舆情预警：过去24小时新增 {neg_count} 条负面信息",
                "type": "sentiment"
            })
            
        # 2. 检查特定高危关键词 (如: 投诉, 维权, 质量问题, 骗子)
        risk_keywords = ['投诉', '维权', '质量', '骗子', '罢工', '起火']
        for kw in risk_keywords:
            kw_sql = "SELECT COUNT(*) as count FROM content WHERE content LIKE ? AND created_at >= ?"
            kw_count_row = query_db(kw_sql, (f'%{kw}%', yesterday), one=True)
            kw_count = kw_count_row['count'] if kw_count_row else 0
            if kw_count > 2:
                new_alerts.append({
                    "level": "medium",
                    "title": f"敏感词预警：监控到关键词「{kw}」出现频率异常 ({kw_count}次)",
                    "type": "keyword"
                })
        
        # 写入数据库 (避免重复生成相同的预警)
        if new_alerts:
            conn = sqlite3.connect(HOTSEARCH_DB_PATH)
            cur = conn.cursor()
            for alert in new_alerts:
                # 检查是否已存在类似的未处理预警
                cur.execute("SELECT id FROM alerts WHERE title = ? AND status = 'unread'", (alert['title'],))
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO alerts (level, title, type) VALUES (?, ?, ?)",
                        (alert['level'], alert['title'], alert['type'])
                    )
            conn.commit()
            conn.close()
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
        # 如果还是没数据，返回一些初始模拟数据
        return [
            {"id": 1, "level": "high", "title": "系统启动：正在初始化监控任务...", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": "read"},
        ]
        
    return [dict(row) for row in results]

@router.post("/read/{alert_id}")
async def mark_as_read(alert_id: int):
    """标记预警为已读/已处理"""
    try:
        conn = sqlite3.connect(HOTSEARCH_DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE alerts SET status = 'read' WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
