import pandas as pd
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..config import MEDIA_CRAWLER_DATA_DIR, IMAGE_EXTENSIONS

class DataManager:
    def __init__(self):
        self.data_dir = MEDIA_CRAWLER_DATA_DIR

    def detect_platform(self, file_path: str) -> str:
        """Identify platform (weibo/zhihu) based on file path."""
        path_str = str(file_path).lower()
        if "weibo" in path_str:
            return "weibo"
        elif "zhihu" in path_str:
            return "zhihu"
        return "unknown"

    def _find_images(self, platform: str, parent_note_id: str, current_id: str, is_post: bool, pictures_str: Optional[str]) -> List[str]:
        """根据新的命名规则查找与帖子或评论关联的本地图片。"""
        if not pictures_str or pd.isna(pictures_str):
            return []
            
        # 图片存储在 data/{platform}/csv/{parent_note_id}/imgs/ 目录下
        # 使用用户要求的相对路径格式：data\weibo\csv\{note_id}\imgs\{filename}
        img_rel_dir = Path("data") / platform / "csv" / parent_note_id / "imgs"
        # 实际磁盘上的绝对路径
        img_abs_dir = self.data_dir.parent / img_rel_dir
        
        if not img_abs_dir.exists():
            # 兼容性处理：有些可能没在 imgs 子目录下
            img_rel_dir_alt = Path("data") / platform / "csv" / parent_note_id
            img_abs_dir_alt = self.data_dir.parent / img_rel_dir_alt
            if img_abs_dir_alt.exists():
                img_rel_dir = img_rel_dir_alt
                img_abs_dir = img_abs_dir_alt
            else:
                return []

        # 图片数量可以通过 pictures_str 中逗号分隔的 URL 数量推断
        num_images = len(str(pictures_str).split(','))
        images = []
        
        if is_post:
            # 文章图片命名规则：note_id.jpg (单张) 或 note_id_1.jpg, note_id_2.jpg... (多张)
            if num_images == 1:
                img_name = f"{current_id}.jpg"
                img_path = img_abs_dir / img_name
                if img_path.exists():
                    images.append(str(img_rel_dir / img_name))
                else:
                    # 备选方案：如果 .jpg 不存在，尝试 _1.jpg
                    img_name_fallback = f"{current_id}_1.jpg"
                    if (img_abs_dir / img_name_fallback).exists():
                        images.append(str(img_rel_dir / img_name_fallback))
            else:
                for i in range(1, num_images + 1):
                    img_name = f"{current_id}_{i}.jpg"
                    if (img_abs_dir / img_name).exists():
                        images.append(str(img_rel_dir / img_name))
        else:
            # 评论图片命名规则：comment_id_1.jpg, comment_id_2.jpg...
            for i in range(1, num_images + 1):
                img_name = f"{current_id}_{i}.jpg"
                if (img_abs_dir / img_name).exists():
                    images.append(str(img_rel_dir / img_name))
                    
        return images

    def load_weibo_data(self, posts_file: str, comments_file: str) -> List[Dict[str, Any]]:
        """加载微博 CSV 数据并返回扁平化的项目列表（包含文章和评论）。"""
        posts_df = pd.read_csv(posts_file)
        comments_df = pd.read_csv(comments_file)
        
        # 优化：按 note_id 对评论进行分组
        comments_by_post = {str(k): g for k, g in comments_df.groupby('note_id')}
        
        flat_items = []
        
        for _, post in posts_df.iterrows():
            note_id = str(post['note_id']) # 文章 ID
            top_id = str(post.get('top_id', note_id)) 
            post_url = post.get('note_url', post.get('url', f"https://m.weibo.cn/detail/{note_id}"))
            post_content = post['content']
            pictures = post.get('pictures', '')
            
            # 1. 添加文章 (Post)
            post_data = {
                "note_id": note_id,
                "comment_id": "0", # 文章的 comment_id 统一设为 "0"
                "top_id": top_id,
                "url": post_url,
                "content": post_content,
                "author": post.get('nickname', ''),
                "created_at": post.get('create_date_time', ''),
                "source": "weibo",
                "type": "post",
                "images": self._find_images("weibo", note_id, note_id, is_post=True, pictures_str=pictures),
                "parent_content": None
            }
            flat_items.append(post_data)
            
            # 2. 添加相关的评论 (Comments)
            if note_id in comments_by_post:
                post_comments = comments_by_post[note_id]
                for _, comm in post_comments.iterrows():
                    comm_id = str(comm['comment_id'])
                    comm_pictures = comm.get('pictures', '')
                    flat_items.append({
                        "note_id": note_id, # 评论的 note_id 必须指向所属文章 ID
                        "comment_id": comm_id,
                        "top_id": top_id,
                        "url": post_url,
                        "content": comm['content'],
                        "author": comm.get('nickname', ''),
                        "created_at": comm.get('create_date_time', ''),
                        "source": "weibo",
                        "type": "comment",
                        "images": self._find_images("weibo", note_id, comm_id, is_post=False, pictures_str=comm_pictures),
                        "parent_content": post_content
                    })
        
        return flat_items

    def load_json_data(self, json_file: str) -> List[Dict[str, Any]]:
        """Load unlabelled JSON data for batch processing."""
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        platform = self.detect_platform(json_file)
        
        # Standardize format if needed
        standardized = []
        for item in data:
            item["source"] = platform
            if "images" not in item:
                # Try to find images if note_id is present
                if "note_id" in item:
                    item["images"] = self._find_images(platform, str(item["note_id"]), str(item["note_id"]))
                else:
                    item["images"] = []
            standardized.append(item)
            
        return standardized
