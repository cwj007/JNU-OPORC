import sqlite3
import os
import json
from pathlib import Path

# 定义 Visualized 模块自己的缓存目录
VISUALIZED_DIR = Path(__file__).parent.parent
CACHE_DIR = VISUALIZED_DIR / "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# 热搜数据存储在 Visualized 自己的缓存中
HOTSEARCH_DB_PATH = CACHE_DIR / "hotsearch.db"

# 舆情内容数据（来自 Transformers）保持在原位置
import sys
# 确保能找到 Transformers 模块
transformers_path = str(Path(__file__).parent.parent.parent)
if transformers_path not in sys.path:
    sys.path.append(transformers_path)

try:
    from Transformers.config import CACHE_DIR as TR_CACHE_DIR
    TRANSFORMERS_DB_PATH = TR_CACHE_DIR / "processed_ids.db"
except ImportError:
    # 回退：硬编码路径
    TRANSFORMERS_DB_PATH = Path(__file__).parent.parent.parent / "Transformers" / "cache" / "processed_ids.db"

# MediaCrawler 数据库路径
MEDIA_CRAWLER_DB_PATH = Path(__file__).parent.parent.parent / "MediaCrawler" / "database" / "sqlite_tables.db"

# 为了向后兼容，保留 DB_PATH，默认指向热搜数据库
DB_PATH = HOTSEARCH_DB_PATH

def init_db():
    """初始化数据库表结构"""
    # 1. 初始化热搜数据库
    try:
        conn = sqlite3.connect(HOTSEARCH_DB_PATH, timeout=30)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS hot_search_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                hot_value TEXT,
                fetch_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rank INTEGER,
                previous_rank INTEGER,
                trend INTEGER,
                is_new INTEGER DEFAULT 0
            )
        ''')
        try:
            cur.execute("ALTER TABLE hot_search_data ADD COLUMN is_new INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Hotsearch database init error: {e}")

    # 3. 初始化预警数据库
    try:
        conn = sqlite3.connect(HOTSEARCH_DB_PATH, timeout=30)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'unread',
                type TEXT
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 初始化一些默认关键词
        cur.execute("INSERT OR IGNORE INTO keywords (tag) VALUES ('千问'), ('免单'), ('奶茶'), ('年货')")
        
        # 4. 初始化监控任务表
        cur.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                group_name TEXT,
                keywords TEXT NOT NULL,
                exclude_words TEXT,
                platforms TEXT,
                warning_enabled INTEGER DEFAULT 0,
                warning_keywords TEXT,
                notify_methods TEXT,
                frequency TEXT DEFAULT 'realtime',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 5. 初始化预警规则表 (新增强化预警中心)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                keyword TEXT,
                threshold INTEGER DEFAULT 100,
                time_window INTEGER DEFAULT 1, -- 单位：小时
                sentiment TEXT DEFAULT '负面',
                is_crisis INTEGER DEFAULT 0, -- 0: 普通, 1: 危机识别 (政治/法律/伦理)
                notify_methods TEXT DEFAULT 'system', -- system,email
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 数据库迁移：确保新列存在
        columns_to_add = [
            ("alert_rules", "keyword", "TEXT"),
            ("alert_rules", "threshold", "INTEGER DEFAULT 100"),
            ("alert_rules", "time_window", "INTEGER DEFAULT 1"),
            ("alert_rules", "sentiment", "TEXT DEFAULT '负面'"),
            ("alert_rules", "is_crisis", "INTEGER DEFAULT 0"),
            ("alert_rules", "notify_methods", "TEXT DEFAULT 'system'"),
            ("alert_rules", "is_active", "INTEGER DEFAULT 1"),
            ("alert_rules", "rule_type", "TEXT DEFAULT 'threshold'"),
            ("alert_rules", "config", "TEXT"),
            ("alerts", "content", "TEXT"),
            ("alerts", "type", "TEXT"),
            ("alerts", "reference_id", "TEXT"),
            ("alerts", "meta_data", "TEXT"),
            ("alerts", "alerts_time", "TEXT")
        ]
        
        for table, col, col_type in columns_to_add:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass # 列已存在
        
        # 初始化一些默认预警规则
        cur.execute("SELECT COUNT(*) FROM alert_rules")
        if cur.fetchone()[0] == 0:
            cur.execute('''
                INSERT INTO alert_rules (name, keyword, threshold, time_window, sentiment, is_crisis, notify_methods)
                VALUES 
                ('负面舆情激增', '', 50, 1, '负面', 0, 'system,email'),
                ('政治敏感监测', '', 1, 24, '负面', 1, 'system,email'),
                ('知乎品牌危机', '知乎', 20, 2, '负面', 0, 'system')
            ''')

        # Check for CRI rule
        cur.execute("SELECT COUNT(*) FROM alert_rules WHERE rule_type = 'cri_trend'")
        if cur.fetchone()[0] == 0:
            default_config = {
                "weights": {
                    "w1": 0.2, "w2": 0.3, "w3": 0.1, "w4": 0.3, "w5": 0.1
                },
                "threshold_sigma": 1.0,
                "veto_enabled": True
            }
            cur.execute('''
                 INSERT INTO alert_rules (name, rule_type, config, notify_methods, keyword, threshold, time_window, sentiment, is_crisis)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
             ''', ('文章舆情趋势预警', 'cri_trend', json.dumps(default_config), 'system', '', 0, 720, '负面', 0))

        # Check for Article Burst rule (new request)
        cur.execute("SELECT COUNT(*) FROM alert_rules WHERE rule_type = 'article_burst'")
        if cur.fetchone()[0] == 0:
            # Default thresholds: 20 comments total, 10 negative comments
            burst_config = {
                "min_comments": 20,
                "min_negative_comments": 10,
                "negative_ratio": 0.3
            }
            # Default time_window set to 720 hours (30 days) to cover history by default
            cur.execute('''
                 INSERT INTO alert_rules (name, rule_type, config, notify_methods, keyword, threshold, time_window, sentiment, is_crisis)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
             ''', ('单贴高危负面预警', 'article_burst', json.dumps(burst_config), 'system', '', 20, 720, '负面', 0))
            
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Alerts/Tasks database init error: {e}")

    # 2. 确保 Transformers 数据库存在（如果不存在则初始化，但通常由 Transformers 模块处理）
    # 这里我们只负责在 Visualized 启动时确保它能读取
    if not TRANSFORMERS_DB_PATH.exists():
        print(f"Warning: Transformers database not found at {TRANSFORMERS_DB_PATH}")

def query_db(query: str, args: tuple = (), one: bool = False):
    """
    智能查询：根据查询表名选择数据库
    """
    # 更加精确地判断目标数据库
    query_lower = query.lower()
    # Transformers 数据库中的表
    tr_tables = ["content", "comments", "top_topics", "processed_items"]
    # MediaCrawler 数据库中的表
    mc_tables = ["weibo_creator", "zhihu_creator"]
    
    target_db = HOTSEARCH_DB_PATH
    
    # 检查是否为 MediaCrawler 表
    for table in mc_tables:
        if table in query_lower:
            target_db = MEDIA_CRAWLER_DB_PATH
            # print(f"DEBUG: Routing query to MediaCrawler DB: {query}")
            break
            
    # 检查是否为 Transformers 表 (如果不匹配 MediaCrawler)
    if target_db == HOTSEARCH_DB_PATH:
        for table in tr_tables:
            # 使用正则表达式或者更精确的边界检查，避免 "content" 作为列名时被误判
            import re
            if re.search(rf'\b{table}\b', query_lower):
                target_db = TRANSFORMERS_DB_PATH
                break

    try:
        conn = sqlite3.connect(target_db, timeout=30)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, args)
        rv = cur.fetchall()
        conn.close()
        return (rv[0] if rv else None) if one else rv
    except sqlite3.OperationalError as e:
        print(f"Database error on {target_db}: {e}")
        return None
    except Exception as e:
        print(f"General query error: {e}")
        return None

def execute_db(query: str, args: tuple = ()):
    """
    执行写操作（INSERT/UPDATE/DELETE）并提交
    """
    query_lower = query.lower()
    tr_tables = ["content", "comments", "top_topics", "processed_items"]
    
    target_db = HOTSEARCH_DB_PATH
    for table in tr_tables:
        import re
        if re.search(rf'\b{table}\b', query_lower):
            # 特殊处理：如果是插入 alerts 表，即使包含 content 列名，也应该去 hotsearch.db
            if "into alerts" in query_lower:
                target_db = HOTSEARCH_DB_PATH
            else:
                target_db = TRANSFORMERS_DB_PATH
            break

    try:
        conn = sqlite3.connect(target_db, timeout=30)
        cur = conn.cursor()
        cur.execute(query, args)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Execute error on {target_db}: {e}")
        return False
