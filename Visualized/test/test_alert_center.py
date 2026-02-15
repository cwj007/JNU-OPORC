import sqlite3
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 确保可以导入 Visualized 模块
sys.path.append(str(Path(__file__).parent.parent.parent))

from Visualized.api.database import init_db, execute_db, query_db, TRANSFORMERS_DB_PATH, HOTSEARCH_DB_PATH
from Visualized.api.alert_engine import AlertEngine

def setup_test_data():
    """准备测试数据"""
    print("Initializing databases...")
    init_db()
    
    # 1. 确保 Transformers 数据库表存在
    conn = sqlite3.connect(TRANSFORMERS_DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS content (
            note_id TEXT PRIMARY KEY,
            title TEXT,
            content TEXT,
            sentiment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 清理旧测试数据
    cur.execute("DELETE FROM content WHERE note_id LIKE 'test_%'")
    
    # 插入一些触发阈值的负面数据
    now = datetime.now()
    for i in range(60):
        cur.execute(
            "INSERT INTO content (note_id, title, content, sentiment, created_at) VALUES (?, ?, ?, ?, ?)",
            (f"test_neg_{i}", f"负面标题 {i}", f"这是一个非常糟糕的体验 {i}，我要投诉！", "负面", (now - timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"))
        )
        
    # 插入一些危机数据 (政治敏感)
    cur.execute(
        "INSERT INTO content (note_id, title, content, sentiment, created_at) VALUES (?, ?, ?, ?, ?)",
        ("test_crisis_1", "敏感话题", "涉及领土主权的讨论...", "负面", now.strftime("%Y-%m-%d %H:%M:%S"))
    )
    
    conn.commit()
    conn.close()
    print("Test data injected into Transformers DB.")

    # 2. 确保预警规则存在
    # init_db 已经插入了一些默认规则，我们检查一下
    rules = query_db("SELECT * FROM alert_rules")
    print(f"Active rules: {[r['name'] for r in rules]}")

def test_alert_engine():
    """测试预警引擎"""
    print("\nRunning Alert Engine...")
    engine = AlertEngine()
    engine.run_check()
    
    # 检查生成的预警
    alerts = query_db("SELECT * FROM alerts ORDER BY time DESC LIMIT 5")
    print("\nRecent Alerts Generated:")
    for alert in alerts:
        alert_dict = dict(alert)
        print(f"[{alert_dict['level'].upper()}] {alert_dict['title']} - {alert_dict['time']}")
        content_text = alert_dict.get('content') or "No content"
        print(f"Content: {content_text[:100]}...")
        print("-" * 30)

    if len(alerts) > 0:
        print("\nTest PASSED: Alerts were successfully generated.")
    else:
        print("\nTest FAILED: No alerts were generated.")

if __name__ == "__main__":
    setup_test_data()
    test_alert_engine()
