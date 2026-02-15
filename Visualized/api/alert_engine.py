import sqlite3
from datetime import datetime, timedelta
import os
from pathlib import Path
from .database import query_db, execute_db, HOTSEARCH_DB_PATH, TRANSFORMERS_DB_PATH

# 危机识别关键词
CRISIS_KEYWORDS = {
    "politics": ["政治", "政策", "政府", "领土", "外交", "主权", "敏感", "违禁"],
    "law": ["法律", "诉讼", "法院", "判决", "违法", "犯罪", "侵权", "官司", "律师"],
    "ethics": ["伦理", "道德", "歧视", "偏见", "骚扰", "霸凌", "虐待", "造假", "丑闻"]
}

class NotificationService:
    @staticmethod
    def notify(method: str, title: str, content: str, level: str):
        methods = method.split(',')
        for m in methods:
            m = m.strip().lower()
            if m == 'system':
                NotificationService._send_system_msg(title, content, level)
            elif m == 'email':
                NotificationService._send_email(title, content, level)

    @staticmethod
    def _send_system_msg(title: str, content: str, level: str):
        """发送站内信"""
        sql = "INSERT INTO alerts (level, title, content, status, type) VALUES (?, ?, ?, 'unread', 'system')"
        execute_db(sql, (level, title, content))
        print(f"[System Notification] {level.upper()}: {title}")

    @staticmethod
    def _send_email(title: str, content: str, level: str):
        """发送邮件 (Mock)"""
        # 在实际系统中，这里会调用 SMTP 服务
        print(f"[Email Notification Sent] To: admin@example.com, Subject: {title}, Level: {level}")

class AlertEngine:
    def __init__(self):
        self.rules = []

    def load_rules(self):
        """加载所有启用的预警规则"""
        sql = "SELECT * FROM alert_rules WHERE is_active = 1"
        results = query_db(sql)
        self.rules = [dict(row) for row in results] if results else []

    def run_check(self):
        """执行预警检查"""
        self.load_rules()
        for rule in self.rules:
            self._check_rule(rule)

    def _check_rule(self, rule: dict):
        """检查单条规则是否触发"""
        time_window = rule['time_window']
        threshold = rule['threshold']
        keyword = rule['keyword']
        sentiment = rule['sentiment']
        is_crisis = rule['is_crisis']
        
        # 计算起始时间
        start_time = (datetime.now() - timedelta(hours=time_window)).strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. 基础条件查询 (情绪 + 关键词 + 时间)
        query = "SELECT COUNT(*) as count FROM content WHERE sentiment = ? AND created_at >= ?"
        params = [sentiment, start_time]
        
        if keyword:
            query += " AND content LIKE ?"
            params.append(f"%{keyword}%")
            
        res = query_db(query, tuple(params), one=True)
        count = res['count'] if res else 0
        
        triggered = False
        reason = ""
        
        # 阈值触发
        if count >= threshold:
            triggered = True
            reason = f"在过去 {time_window} 小时内，检测到 {count} 条{sentiment}舆情，达到阈值 {threshold}。"
            
        # 2. 危机识别触发 (如果是危机规则)
        if is_crisis:
            # 搜索所有危机关键词
            all_crisis_kws = [kw for sub in CRISIS_KEYWORDS.values() for kw in sub]
            crisis_found = False
            found_kws = []
            
            # 这里的查询可能会比较重，实际生产环境建议索引优化或使用全文检索
            for kw in all_crisis_kws:
                crisis_query = "SELECT COUNT(*) as count FROM content WHERE (content LIKE ? OR title LIKE ?) AND created_at >= ?"
                c_res = query_db(crisis_query, (f"%{kw}%", f"%{kw}%", start_time), one=True)
                if c_res and c_res['count'] > 0:
                    crisis_found = True
                    found_kws.append(kw)
            
            if crisis_found:
                triggered = True
                level = "high"
                title = f"【危机预警】{rule['name']}"
                content = f"检测到涉及敏感领域({', '.join(found_kws)})的内容。触发规则: {rule['name']}。"
                NotificationService.notify(rule['notify_methods'], title, content, level)
                return # 危机预警优先处理

        if triggered:
            level = "high" if count > threshold * 2 else "medium"
            title = f"【阈值预警】{rule['name']}"
            content = f"{reason} 规则名称: {rule['name']}。"
            NotificationService.notify(rule['notify_methods'], title, content, level)

def run_alert_engine():
    """便捷启动函数"""
    engine = AlertEngine()
    engine.run_check()

if __name__ == "__main__":
    run_alert_engine()
