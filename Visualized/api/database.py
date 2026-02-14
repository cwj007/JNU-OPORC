import sqlite3
import os
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
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Alerts database init error: {e}")

    # 2. 确保 Transformers 数据库存在（如果不存在则初始化，但通常由 Transformers 模块处理）
    # 这里我们只负责在 Visualized 启动时确保它能读取
    if not TRANSFORMERS_DB_PATH.exists():
        print(f"Warning: Transformers database not found at {TRANSFORMERS_DB_PATH}")

def query_db(query: str, args: tuple = (), one: bool = False):
    """
    智能查询：根据查询表名选择数据库
    """
    # 简单判断查询的目标表
    target_db = HOTSEARCH_DB_PATH
    if "content" in query.lower() or "comments" in query.lower() or "top_topics" in query.lower():
        target_db = TRANSFORMERS_DB_PATH

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
