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
        
        # Preprocessing to ensure consistent types
        posts_df['note_id'] = posts_df['note_id'].astype(str)
        posts_df = posts_df.where(pd.notnull(posts_df), None)
        
        comments_df['note_id'] = comments_df['note_id'].astype(str)
        comments_df['comment_id'] = comments_df['comment_id'].astype(str)
        comments_df = comments_df.where(pd.notnull(comments_df), None)
        
        return posts_df.to_dict('records'), comments_df.to_dict('records')

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

