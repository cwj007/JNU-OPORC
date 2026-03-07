import sqlite3
import os
import json
import re
import asyncio
import aiosqlite
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

# 预编译正则以提高性能
RE_TABLE_BOUNDARIES = {}

def get_target_db(query: str) -> Path:
    """根据查询内容智能选择数据库路径"""
    query_lower = query.lower()
    
    # MediaCrawler 数据库中的表
    mc_tables = ["weibo_creator", "zhihu_creator"]
    for table in mc_tables:
        if table not in RE_TABLE_BOUNDARIES:
            RE_TABLE_BOUNDARIES[table] = re.compile(rf'\b{table}\b')
        if RE_TABLE_BOUNDARIES[table].search(query_lower):
            return MEDIA_CRAWLER_DB_PATH
            
    # Transformers 数据库中的表
    tr_tables = ["content", "comments", "top_topics"]
    for table in tr_tables:
        if table not in RE_TABLE_BOUNDARIES:
            RE_TABLE_BOUNDARIES[table] = re.compile(rf'\b{table}\b')
        if RE_TABLE_BOUNDARIES[table].search(query_lower):
            # 特殊处理：如果是插入 alerts 表，即使包含 content 列名，也应该去 hotsearch.db
            if "into alerts" in query_lower:
                return HOTSEARCH_DB_PATH
            return TRANSFORMERS_DB_PATH
            
    return HOTSEARCH_DB_PATH

async def init_wal(db_path: Path):
    """初始化数据库为 WAL 模式以提高并发性能"""
    if not db_path.exists():
        return
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.commit()
    except Exception as e:
        print(f"Failed to enable WAL for {db_path}: {e}")

def init_db():
    """初始化数据库表结构"""
    # 确保 WAL 模式开启
    for db in [HOTSEARCH_DB_PATH, TRANSFORMERS_DB_PATH, MEDIA_CRAWLER_DB_PATH]:
        if db.exists():
            conn = sqlite3.connect(db)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.close()

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
            ("alerts", "alerts_time", "TEXT"),
            ("alerts", "user_id", "INTEGER"),
            ("monitoring_tasks", "user_id", "INTEGER"),
            ("alert_rules", "user_id", "INTEGER"),
            ("alerts", "processed", "INTEGER DEFAULT 0")
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
            
        # 索引优化：提高查询性能
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_reference_id ON alerts(reference_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_monitoring_tasks_user_id ON monitoring_tasks(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_alert_rules_user_id ON alert_rules(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hotsearch_fetch_time ON hot_search_data(fetch_time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hotsearch_platform_rank ON hot_search_data(platform, rank)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hotsearch_platform_fetch_rank ON hot_search_data(platform, fetch_time, rank)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hotsearch_platform_fetch ON hot_search_data(platform, fetch_time)")
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Alerts/Tasks database init error: {e}")

            # 5.5 初始化内容数据库索引 (Transformers)
    try:
        if TRANSFORMERS_DB_PATH.exists():
            conn = sqlite3.connect(TRANSFORMERS_DB_PATH, timeout=30)
            cur = conn.cursor()
            
            # 检查列是否存在，防止索引创建失败
            cur.execute("PRAGMA table_info(content)")
            content_cols = [col[1] for col in cur.fetchall()]
            
            cur.execute("PRAGMA table_info(comments)")
            comments_cols = [col[1] for col in cur.fetchall()]

            if "note_id" in content_cols:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_content_note_id ON content(note_id)")
            if "fetch_time" in content_cols:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_content_fetch_time ON content(fetch_time)")
            if "created_at" in content_cols:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_content_created_at ON content(created_at)")
            if "source" in content_cols:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_content_source ON content(source)")
            
            if "note_id" in comments_cols:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_note_id ON comments(note_id)")
            if "created_at" in comments_cols:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_created_at ON comments(created_at)")
            if "sentiment" in comments_cols:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_sentiment ON comments(sentiment)")
            
            # 初始化 FTS5 全文搜索表 (针对 content 和 comments)
            # 使用 content 选项以减少存储空间，引用原始表的 rowid
            cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(title, content, content='content', content_rowid='rowid')")
            cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS comments_fts USING fts5(content, content='comments', content_rowid='rowid')")
            
            # 创建触发器以自动同步 FTS 数据
            # content 表触发器
            cur.execute("DROP TRIGGER IF EXISTS content_ai")
            cur.execute("""
                CREATE TRIGGER content_ai AFTER INSERT ON content BEGIN
                    INSERT INTO content_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content);
                END;
            """)
            cur.execute("DROP TRIGGER IF EXISTS content_ad")
            cur.execute("""
                CREATE TRIGGER content_ad AFTER DELETE ON content BEGIN
                    INSERT INTO content_fts(content_fts, rowid, title, content) VALUES('delete', old.rowid, old.title, old.content);
                END;
            """)
            cur.execute("DROP TRIGGER IF EXISTS content_au")
            cur.execute("""
                CREATE TRIGGER content_au AFTER UPDATE ON content BEGIN
                    INSERT INTO content_fts(content_fts, rowid, title, content) VALUES('delete', old.rowid, old.title, old.content);
                    INSERT INTO content_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content);
                END;
            """)
            
            # comments 表触发器
            cur.execute("DROP TRIGGER IF EXISTS comments_ai")
            cur.execute("""
                CREATE TRIGGER comments_ai AFTER INSERT ON comments BEGIN
                    INSERT INTO comments_fts(rowid, content) VALUES (new.rowid, new.content);
                END;
            """)
            cur.execute("DROP TRIGGER IF EXISTS comments_ad")
            cur.execute("""
                CREATE TRIGGER comments_ad AFTER DELETE ON comments BEGIN
                    INSERT INTO comments_fts(comments_fts, rowid, content) VALUES('delete', old.rowid, old.content);
                END;
            """)
            cur.execute("DROP TRIGGER IF EXISTS comments_au")
            cur.execute("""
                CREATE TRIGGER comments_au AFTER UPDATE ON comments BEGIN
                    INSERT INTO comments_fts(comments_fts, rowid, content) VALUES('delete', old.rowid, old.content);
                    INSERT INTO comments_fts(rowid, content) VALUES (new.rowid, new.content);
                END;
            """)
            
            # 首次运行时填充 FTS 数据
            cur.execute("SELECT COUNT(*) FROM content_fts")
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO content_fts(rowid, title, content) SELECT rowid, title, content FROM content")
            
            cur.execute("SELECT COUNT(*) FROM comments_fts")
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO comments_fts(rowid, content) SELECT rowid, content FROM comments")
            
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Transformers database index error: {e}")
        import traceback
        traceback.print_exc()

    # 6. 初始化用户表 (Authentication)
    try:
        conn = sqlite3.connect(HOTSEARCH_DB_PATH, timeout=30)
        cur = conn.cursor()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT DEFAULT 'user', -- 'admin' or 'user'
                email TEXT,
                email_notify_enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 7. User Favorites for Hotsearch
        cur.execute('''
            CREATE TABLE IF NOT EXISTS user_platform_follows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                platform_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, platform_id)
            )
        ''')
         
        # Check if salt column exists (migration)
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        if 'salt' not in columns:
             try:
                 cur.execute("ALTER TABLE users ADD COLUMN salt TEXT DEFAULT ''")
             except sqlite3.OperationalError:
                 pass
        
        if 'email' not in columns:
            try:
                cur.execute("ALTER TABLE users ADD COLUMN email TEXT")
            except sqlite3.OperationalError:
                pass
                
        if 'email_notify_enabled' not in columns:
            try:
                cur.execute("ALTER TABLE users ADD COLUMN email_notify_enabled INTEGER DEFAULT 1")
            except sqlite3.OperationalError:
                pass
                 
        # Check if root admin exists, if not create default
        cur.execute("SELECT COUNT(*) FROM users WHERE username = 'root'")
        if cur.fetchone()[0] == 0:
            import hashlib
            import secrets
            salt = secrets.token_hex(16)
            # Default password: 123456
            pwd_hash = hashlib.pbkdf2_hmac('sha256', '123456'.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
            cur.execute("INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)", ('root', pwd_hash, salt, 'admin'))
            
        # 7. 初始化会话表 (Sessions)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')

        # 9. 初始化通知记录表 (Notification Log)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS notifications_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                rule_id INTEGER,
                reference_id TEXT, -- 触发标识（如文章 note_id 或时间戳）
                type TEXT NOT NULL, -- 'system', 'email'
                target TEXT, -- 目标（如邮箱地址）
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, rule_id, reference_id, type)
            )
        ''')

        # 8. Add user_id to existing tables if needed (migration)
        # monitoring_tasks
        try:
            cur.execute("ALTER TABLE monitoring_tasks ADD COLUMN user_id INTEGER")
        except sqlite3.OperationalError:
            pass
            
        # alert_rules
        try:
            cur.execute("ALTER TABLE alert_rules ADD COLUMN user_id INTEGER")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Auth database init error: {e}")

    # 2. 确保 Transformers 数据库存在并初始化索引
    if TRANSFORMERS_DB_PATH.exists():
        try:
            conn = sqlite3.connect(TRANSFORMERS_DB_PATH, timeout=30)
            cur = conn.cursor()
            # 为 content 和 comments 表的 created_at 字段创建索引以提高查询性能
            cur.execute("CREATE INDEX IF NOT EXISTS idx_content_created_at ON content(created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_created_at ON comments(created_at)")
            # 同时为 note_id 创建索引（如果尚未存在）以提高关联查询性能
            cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_note_id ON comments(note_id)")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Transformers database index optimization error: {e}")
    else:
        print(f"Warning: Transformers database not found at {TRANSFORMERS_DB_PATH}")

# 数据库连接缓存
_connections = {}

async def get_db_connection(db_path: Path):
    """获取或创建一个数据库连接"""
    if db_path not in _connections:
        # aiosqlite.connect 是一个异步上下文管理器，不能直接放入字典
        # 我们这里使用 aiosqlite.connect 直接创建连接
        conn = await aiosqlite.connect(db_path, timeout=30)
        # 开启 WAL 模式提高并发
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA group_concat_max_len = 1000000")
        _connections[db_path] = conn
    return _connections[db_path]

async def close_all_connections():
    """关闭所有缓存的数据库连接"""
    for conn in _connections.values():
        await conn.close()
    _connections.clear()

async def query_db(query: str, args: tuple = (), one: bool = False):
    """
    异步智能查询：根据查询表名选择数据库
    """
    target_db = get_target_db(query)
    
    try:
        # 使用连接缓存以提高性能
        db = await get_db_connection(target_db)
        db.row_factory = aiosqlite.Row
        async with db.execute(query, args) as cursor:
            rv = await cursor.fetchall()
            if one:
                return dict(rv[0]) if rv else None
            return [dict(row) for row in rv] if rv else []
    except Exception as e:
        print(f"Async query error on {target_db}: {e}")
        # 如果连接失效，尝试清除缓存并重试一次
        if target_db in _connections:
            try:
                await _connections[target_db].close()
            except:
                pass
            del _connections[target_db]
        return None

async def execute_db(query: str, args: tuple = ()):
    """
    异步执行写操作（INSERT/UPDATE/DELETE）并提交
    """
    target_db = get_target_db(query)

    try:
        # 使用连接缓存以提高性能
        db = await get_db_connection(target_db)
        await db.execute(query, args)
        await db.commit()
        return True
    except Exception as e:
        print(f"Async execute error on {target_db}: {e}")
        # 如果连接失效，尝试清除缓存并重试一次
        if target_db in _connections:
            try:
                await _connections[target_db].close()
            except:
                pass
            del _connections[target_db]
        return False

def query_db_sync(query: str, args: tuple = (), one: bool = False):
    """
    同步智能查询（保留用于非异步场景）
    """
    target_db = get_target_db(query)
    try:
        conn = sqlite3.connect(target_db, timeout=30)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(query, args)
            rv = cur.fetchall()
            if one:
                return dict(rv[0]) if rv else None
            return [dict(row) for row in rv] if rv else []
        finally:
            conn.close()
    except Exception as e:
        print(f"Sync query error: {e}")
        return None

def execute_db_sync(query: str, args: tuple = ()):
    """
    同步写操作（保留用于非异步场景）
    """
    target_db = get_target_db(query)
    try:
        conn = sqlite3.connect(target_db, timeout=30)
        try:
            cur = conn.cursor()
            cur.execute(query, args)
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"Sync execute error: {e}")
        return False
