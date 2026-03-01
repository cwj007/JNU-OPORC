import asyncio
import os
import sys
import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Set, Tuple, Optional
from pathlib import Path
from sqlalchemy import select

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent))

from MediaCrawler.database.models import WeiboNote, WeiboNoteComment, ZhihuContent, ZhihuComment
from MediaCrawler.config import db_config
from Transformers import utils

class BaseDataLoader(ABC):
    """Abstract base class for data loaders."""
    
    @abstractmethod
    def load_data(self, **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Load data from source.
        Returns:
            Tuple[List[Dict], List[Dict]]: (posts_data, comments_data)
        """
        pass

class WeiboCSVLoader(BaseDataLoader):
    """Loader for Weibo data from CSV files."""
    
    def load_data(self, posts_file: str, comments_file: str, **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Load data from CSV files."""
        utils.logger.info(f"[WeiboCSVLoader] Loading posts from {posts_file}")
        posts_df = pd.read_csv(posts_file, on_bad_lines='warn', engine='python', encoding='utf-8-sig')
        
        utils.logger.info(f"[WeiboCSVLoader] Loading comments from {comments_file}")
        comments_df = pd.read_csv(comments_file, on_bad_lines='warn', engine='python', encoding='utf-8-sig')
        
        # Define expected columns based on user spec
        post_columns = [
            'id', 'user_id', 'nickname', 'avatar', 'gender', 'profile_url', 'ip_location', 
            'add_ts', 'last_modify_ts', 'note_id', 'content', 'create_time', 'create_date_time', 
            'liked_count', 'comments_count', 'shared_count', 'note_url', 'source_keyword', 
            'top_id', 'pictures', 'video_url'
        ]
        
        comment_columns = [
            'id', 'user_id', 'nickname', 'avatar', 'gender', 'profile_url', 'ip_location', 
            'add_ts', 'last_modify_ts', 'comment_id', 'note_id', 'content', 'create_time', 
            'create_date_time', 'comment_like_count', 'sub_comment_count', 'parent_comment_id', 
            'pictures'
        ]
        
        # Filter/Select columns that exist in the dataframe
        posts_df = posts_df[[c for c in post_columns if c in posts_df.columns]]
        comments_df = comments_df[[c for c in comment_columns if c in comments_df.columns]]
        
        # Preprocessing to ensure consistent types
        if 'note_id' in posts_df.columns:
            posts_df['note_id'] = posts_df['note_id'].astype(str)
        
        posts_df = posts_df.where(pd.notnull(posts_df), None)
        
        if 'note_id' in comments_df.columns:
            comments_df['note_id'] = comments_df['note_id'].astype(str)
        if 'comment_id' in comments_df.columns:
            comments_df['comment_id'] = comments_df['comment_id'].astype(str)
            
        comments_df = comments_df.where(pd.notnull(comments_df), None)
        
        return posts_df.to_dict('records'), comments_df.to_dict('records')

class ZhihuCSVLoader(BaseDataLoader):
    """Loader for Zhihu data from CSV files."""
    
    def load_data(self, posts_file: str, comments_file: str, **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Load data from CSV files."""
        utils.logger.info(f"[ZhihuCSVLoader] Loading posts from {posts_file}")
        posts_df = pd.read_csv(posts_file, on_bad_lines='warn', engine='python', encoding='utf-8-sig')
        
        comments_df = pd.DataFrame()
        if comments_file and os.path.exists(comments_file):
            utils.logger.info(f"[ZhihuCSVLoader] Loading comments from {comments_file}")
            comments_df = pd.read_csv(comments_file, on_bad_lines='warn', engine='python', encoding='utf-8-sig')
        
        # Define expected columns based on user spec
        post_columns = [
            'id', 'content_id', 'content_type', 'content_text', 'content_url', 'question_id', 
            'title', 'desc', 'created_time', 'updated_time', 'voteup_count', 'comment_count', 
            'source_keyword', 'user_id', 'user_link', 'user_nickname', 'user_avatar', 
            'user_url_token', 'add_ts', 'last_modify_ts'
        ]
        
        comment_columns = [
            'id', 'comment_id', 'parent_comment_id', 'content', 'publish_time', 'ip_location', 
            'sub_comment_count', 'like_count', 'dislike_count', 'content_id', 'content_type', 
            'user_id', 'user_link', 'user_nickname', 'user_avatar', 'add_ts', 'last_modify_ts'
        ]
        
        # Filter/Select columns that exist in the dataframe
        posts_df = posts_df[[c for c in post_columns if c in posts_df.columns]]
        if not comments_df.empty:
            comments_df = comments_df[[c for c in comment_columns if c in comments_df.columns]]
        
        # Preprocessing
        if 'content_id' in posts_df.columns:
            posts_df['content_id'] = posts_df['content_id'].astype(str)
            
        posts_df = posts_df.where(pd.notnull(posts_df), None)
        
        if not comments_df.empty:
            if 'content_id' in comments_df.columns:
                comments_df['content_id'] = comments_df['content_id'].astype(str)
            if 'comment_id' in comments_df.columns:
                comments_df['comment_id'] = comments_df['comment_id'].astype(str)
            comments_df = comments_df.where(pd.notnull(comments_df), None)
            
        return posts_df.to_dict('records'), comments_df.to_dict('records')


import json
from datetime import datetime

class ZhihuJSONLoader(BaseDataLoader):
    """Loader for Zhihu data from JSON files."""
    
    def load_data(self, json_file: str, **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Load data from JSON file."""
        utils.logger.info(f"[ZhihuJSONLoader] Loading data from {json_file}")
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        posts_data = []
        comments_data = [] # JSON structure seems to be flat list of contents (answers/articles)
        
        for item in data:
            # Convert timestamp to datetime string
            created_time = item.get('created_time', 0)
            if created_time:
                dt = datetime.fromtimestamp(created_time)
                create_date_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                create_date_time = ""
                
            post = {
                "note_id": str(item.get('content_id')),
                "user_id": str(item.get('user_id')),
                "nickname": item.get('user_nickname'),
                "avatar": item.get('user_avatar'),
                "title": item.get('title'),
                "content": item.get('content_text'),
                "desc": item.get('desc'),
                "note_url": item.get('content_url'),
                "create_date_time": create_date_time,
                "liked_count": item.get('voteup_count', 0),
                "comments_count": item.get('comment_count', 0),
                "question_id": item.get('question_id'),
                "type": item.get('content_type')
            }
            posts_data.append(post)
            
        return posts_data, comments_data

class WeiboJSONLoader(BaseDataLoader):
    """Loader for Weibo data from JSON files."""
    
    def load_data(self, json_path: str, **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Load data from JSON files.
        Args:
            json_path: Path to a specific file or directory containing JSON files.
                       If directory, expects structure like {note_id}/contents.json and comments.json
        """
        utils.logger.info(f"[WeiboJSONLoader] Loading data from {json_path}")
        
        posts_data = []
        comments_data = []
        
        path_obj = Path(json_path)
        
        files_to_process = []
        if path_obj.is_file():
            files_to_process = [path_obj]
        elif path_obj.is_dir():
            # Find all contents.json files
            # Structure: data/weibo/json/{note_id}/contents.json
            files_to_process = list(path_obj.rglob("contents.json"))
            if not files_to_process:
                 # Fallback: maybe the directory itself contains json files directly not named contents.json?
                 # But sticking to the observed structure first.
                 utils.logger.warning(f"[WeiboJSONLoader] No 'contents.json' files found in {json_path}")
        else:
            raise ValueError(f"Invalid path: {json_path}")
            
        # Use sets to track seen content hashes and IDs for deduplication
        seen_post_hashes = set()
        seen_comment_hashes = set()
        seen_post_ids = set()
        seen_comment_ids = set()

        import hashlib

        for content_file in files_to_process:
            try:
                with open(content_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Ensure data is list
                current_posts = []
                if isinstance(data, list):
                    current_posts = data
                elif isinstance(data, dict):
                    current_posts = [data]
                
                # Standardize fields if necessary (Weibo JSON seems to match well, but let's be safe)
                for post in current_posts:
                    note_id = str(post.get('note_id', ''))
                    if not note_id:
                        continue
                    
                    # Deduplicate by ID
                    if note_id in seen_post_ids:
                        continue
                    
                    # Deduplicate by content hash
                    content = post.get('content', '')
                    content_hash = hashlib.md5(str(content).encode('utf-8')).hexdigest()
                    if content_hash in seen_post_hashes:
                        continue
                    
                    post['note_id'] = note_id
                    posts_data.append(post)
                    seen_post_ids.add(note_id)
                    seen_post_hashes.add(content_hash)
                
                # Try to find corresponding comments.json
                # Usually in the same directory
                comment_file = content_file.parent / "comments.json"
                if comment_file.exists():
                    with open(comment_file, 'r', encoding='utf-8') as f:
                        c_data = json.load(f)
                        
                    current_comments = []
                    if isinstance(c_data, list):
                        current_comments = c_data
                    elif isinstance(c_data, dict):
                        current_comments = [c_data]
                        
                    for comment in current_comments:
                        comment_id = str(comment.get('comment_id', ''))
                        if not comment_id:
                            continue
                            
                        # Deduplicate by ID
                        if comment_id in seen_comment_ids:
                            continue
                            
                        # Deduplicate by content hash
                        content = comment.get('content', '')
                        content_hash = hashlib.md5(str(content).encode('utf-8')).hexdigest()
                        if content_hash in seen_comment_hashes:
                            continue
                            
                        comment['comment_id'] = comment_id
                        if 'note_id' in comment:
                            comment['note_id'] = str(comment['note_id'])
                        if 'parent_comment_id' in comment and comment['parent_comment_id']:
                            comment['parent_comment_id'] = str(comment['parent_comment_id'])
                            
                        comments_data.append(comment)
                        seen_comment_ids.add(comment_id)
                        seen_comment_hashes.add(content_hash)
                        
            except Exception as e:
                utils.logger.error(f"[WeiboJSONLoader] Error loading {content_file}: {e}")
                continue
                
        utils.logger.info(f"[WeiboJSONLoader] Loaded {len(posts_data)} posts and {len(comments_data)} comments from {json_path}")
        return posts_data, comments_data

class WeiboSQLiteLoader(BaseDataLoader):
    """Loader for Weibo data from SQLite database."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or db_config.SQLITE_DB_PATH
        
    async def _load_data_async(self, date: str = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Async implementation of data loading."""
        
        # Manually create engine to ensure we use SQLite
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        
        # Use the configured SQLite path
        db_url = f"sqlite+aiosqlite:///{self.db_path}"
        engine = create_async_engine(db_url, echo=False)
        AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        posts_data = []
        comments_data = []
        
        try:
            async with AsyncSessionFactory() as session:
                # Build queries
                post_query = select(WeiboNote)
                comment_query = select(WeiboNoteComment)
                
                # Filter by date if provided
                if date:
                    post_query = post_query.where(WeiboNote.create_date_time.contains(date))
                    comment_query = comment_query.where(WeiboNoteComment.create_date_time.contains(date))
                
                # Execute queries
                utils.logger.info(f"[WeiboSQLiteLoader] Querying WeiboNote from {self.db_path}...")
                post_result = await session.execute(post_query)
                posts = post_result.scalars().all()
                
                utils.logger.info(f"[WeiboSQLiteLoader] Querying WeiboNoteComment from {self.db_path}...")
                comment_result = await session.execute(comment_query)
                comments = comment_result.scalars().all()
                
                # Convert to dicts matching CSV format
                for post in posts:
                    posts_data.append({
                        "note_id": str(post.note_id),
                        "user_id": str(post.user_id),
                        "nickname": post.nickname,
                        "avatar": post.avatar,
                        "gender": post.gender,
                        "profile_url": post.profile_url,
                        "ip_location": post.ip_location,
                        "content": post.content,
                        "create_time": post.create_time,
                        "create_date_time": post.create_date_time,
                        "liked_count": post.liked_count,
                        "comments_count": post.comments_count,
                        "shared_count": post.shared_count,
                        "note_url": post.note_url,
                        "source_keyword": post.source_keyword,
                        "top_id": str(post.top_id) if post.top_id else None,
                        "pictures": post.pictures,
                        "video_url": post.video_url,
                    })
                    
                for comment in comments:
                    comments_data.append({
                        "comment_id": str(comment.comment_id),
                        "note_id": str(comment.note_id),
                        "user_id": str(comment.user_id),
                        "nickname": comment.nickname,
                        "avatar": comment.avatar,
                        "gender": comment.gender,
                        "profile_url": comment.profile_url,
                        "ip_location": comment.ip_location,
                        "content": comment.content,
                        "create_time": comment.create_time,
                        "create_date_time": comment.create_date_time,
                        "comment_like_count": comment.comment_like_count,
                        "sub_comment_count": comment.sub_comment_count,
                        "parent_comment_id": str(comment.parent_comment_id) if comment.parent_comment_id else None,
                        "pictures": comment.pictures,
                    })
        except Exception as e:
            utils.logger.error(f"[WeiboSQLiteLoader] Error loading data: {e}")
            raise
        finally:
            await engine.dispose()
            
        return posts_data, comments_data

    def load_data(self, date: str = None, **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Sync wrapper for async load."""
        return asyncio.run(self._load_data_async(date))

class ZhihuSQLiteLoader(BaseDataLoader):
    """Loader for Zhihu data from SQLite database."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or db_config.SQLITE_DB_PATH
        
    async def _load_data_async(self, date: str = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Async implementation of data loading."""
        
        # Manually create engine to ensure we use SQLite
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        
        # Use the configured SQLite path
        db_url = f"sqlite+aiosqlite:///{self.db_path}"
        engine = create_async_engine(db_url, echo=False)
        AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        posts_data = []
        comments_data = []
        
        try:
            async with AsyncSessionFactory() as session:
                # Build queries
                post_query = select(ZhihuContent)
                comment_query = select(ZhihuComment)
                
                # Filter by date if provided
                if date:
                    post_query = post_query.where(ZhihuContent.created_time.contains(date))
                    comment_query = comment_query.where(ZhihuComment.publish_time.contains(date))
                
                # Execute queries
                utils.logger.info(f"[ZhihuSQLiteLoader] Querying ZhihuContent from {self.db_path}...")
                post_result = await session.execute(post_query)
                posts = post_result.scalars().all()
                
                utils.logger.info(f"[ZhihuSQLiteLoader] Querying ZhihuComment from {self.db_path}...")
                comment_result = await session.execute(comment_query)
                comments = comment_result.scalars().all()
                
                # Convert to dicts matching standard format
                # Mapping Zhihu fields to standard fields used in DataManager
                for post in posts:
                    posts_data.append({
                        "note_id": str(post.content_id), # Map content_id to note_id
                        "user_id": str(post.user_id),
                        "nickname": post.user_nickname,
                        "avatar": post.user_avatar,
                        "gender": None, # ZhihuContent doesn't have gender
                        "profile_url": post.user_link,
                        "ip_location": None, # ZhihuContent doesn't have ip_location
                        "content": post.content_text,
                        "create_time": None, # Only string time available
                        "create_date_time": post.created_time,
                        "liked_count": post.voteup_count,
                        "comments_count": post.comment_count,
                        "shared_count": 0, # Not available
                        "note_url": post.content_url,
                        "source_keyword": post.source_keyword,
                        "top_id": None,
                        "pictures": None, # ZhihuContent doesn't have pictures field in model shown
                        "video_url": None,
                        "title": post.title,
                        "desc": post.desc,
                        "type": post.content_type
                    })
                    
                for comment in comments:
                    comments_data.append({
                        "comment_id": str(comment.comment_id),
                        "note_id": str(comment.content_id), # Map content_id to note_id
                        "user_id": str(comment.user_id),
                        "nickname": comment.user_nickname,
                        "avatar": comment.user_avatar,
                        "gender": None,
                        "profile_url": comment.user_link,
                        "ip_location": comment.ip_location,
                        "content": comment.content,
                        "create_time": None,
                        "create_date_time": comment.publish_time,
                        "comment_like_count": comment.like_count,
                        "sub_comment_count": comment.sub_comment_count,
                        "parent_comment_id": str(comment.parent_comment_id) if comment.parent_comment_id else None,
                        "pictures": None,
                    })
        except Exception as e:
            utils.logger.error(f"[ZhihuSQLiteLoader] Error loading data: {e}")
            raise
        finally:
            await engine.dispose()
            
        return posts_data, comments_data

    def load_data(self, date: str = None, **kwargs) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Sync wrapper for async load."""
        return asyncio.run(self._load_data_async(date))

