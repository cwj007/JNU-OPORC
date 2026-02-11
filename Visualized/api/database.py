import sqlite3
import os
from pathlib import Path
from Transformers.config import CACHE_DIR

DB_PATH = CACHE_DIR / "processed_ids.db"

def init_db():
    """初始化数据库表结构"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # 创建热搜数据表
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
                trend TEXT
            )
        ''')
        
        # 创建内容表 (content)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS content (
                note_id TEXT PRIMARY KEY,
                title TEXT,
                content TEXT,
                author TEXT,
                source TEXT,
                url TEXT,
                created_at TEXT,
                ip_location TEXT,
                image_paths TEXT,
                video_path TEXT,
                liked_count INTEGER,
                comments_count INTEGER,
                shared_count INTEGER,
                collected_count INTEGER,
                sentiment TEXT,
                fine_grained_sentiment TEXT,
                intent TEXT,
                irony_detected BOOLEAN,
                reasoning TEXT,
                keywords TEXT,
                visual_objects TEXT,
                ocr_text TEXT,
                sync_date TEXT DEFAULT (date('now'))
            )
        ''')

        # 创建评论表 (comments)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT PRIMARY KEY,
                note_id TEXT,
                content TEXT,
                author TEXT,
                source TEXT,
                url TEXT,
                created_at TEXT,
                ip_location TEXT,
                gender TEXT,
                parent_comment_id TEXT,
                comment_like_count INTEGER,
                sub_comment_count INTEGER,
                image_paths TEXT,
                sentiment TEXT,
                fine_grained_sentiment TEXT,
                intent TEXT,
                irony_detected BOOLEAN,
                reasoning TEXT,
                labels TEXT,
                keywords TEXT,
                visual_objects TEXT,
                ocr_text TEXT,
                sync_date TEXT DEFAULT (date('now')),
                FOREIGN KEY (note_id) REFERENCES content(note_id)
            )
        ''')

        # 创建 top_topics 表
        cur.execute('''
            CREATE TABLE IF NOT EXISTS top_topics (
                top_id TEXT PRIMARY KEY,
                top_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建索引以提高查询效率
        cur.execute('CREATE INDEX IF NOT EXISTS idx_platform_time ON hot_search_data (platform, fetch_time)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_content_date ON content (created_at)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_comments_date ON comments (created_at)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_comments_note ON comments (note_id)')
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database init error: {e}")

def query_db(query: str, args: tuple = (), one: bool = False):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, args)
        rv = cur.fetchall()
        conn.close()
        return (rv[0] if rv else None) if one else rv
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        return None
    except Exception as e:
        print(f"General query error: {e}")
        return None
