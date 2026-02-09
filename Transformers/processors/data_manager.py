import pandas as pd
import json
import os
import httpx
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

    def _download_image(self, url: str, save_path: Path):
        """如果图片不存在，则通过代理下载。"""
        if save_path.exists():
            return True
            
        # 微博图片防盗链处理：使用 i1.wp.com 代理
        # 参考 MediaCrawler/media_platform/weibo/client.py
        processed_url = url
        if "sinaimg.cn" in url:
            if "://" in url:
                clean_url = url.split("://", 1)[1]
            else:
                clean_url = url
            # 替换为 large 尺寸以获取高清图
            sub_parts = clean_url.split("/")
            if len(sub_parts) >= 3:
                sub_parts[1] = "large"
            processed_url = f"https://i1.wp.com/{'/'.join(sub_parts)}"

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://weibo.com/'
            }
            # 使用 httpx 进行同步下载
            with httpx.Client(follow_redirects=True, timeout=20.0) as client:
                response = client.get(processed_url, headers=headers)
                if response.status_code == 200:
                    with open(save_path, 'wb') as f:
                        f.write(response.content)
                    return True
                else:
                    print(f"Failed to download {processed_url}, status: {response.status_code}")
        except Exception as e:
            print(f"Error downloading {url} via {processed_url}: {e}")
        return False

    def _find_images(self, platform: str, parent_note_id: str, current_id: str, is_post: bool, pictures_str: Optional[str]) -> List[str]:
        """
        严格根据图片清洗规则查找或下载图片：
        1. 文章图片：data/weibo/csv/{note_id}/{note_id}.jpg (单图) 或 {note_id}_1.jpg... (多图)
        2. 评论图片：始终以 {comment_id}_1.jpg 起始命名，多图按顺序
        3. 如果路径中已存在图片（包括旧版 /imgs/ 目录），则不再重复下载
        """
        if not pictures_str or pd.isna(pictures_str):
            return []
        
        # 解析 URL 列表
        urls = [u.strip() for u in str(pictures_str).split(',') if u.strip()]
        if not urls:
            return []
            
        images = []
        # 标准存储目录: MediaCrawler/data/weibo/csv/{note_id}/
        base_dir = self.data_dir / platform / "csv" / parent_note_id
        # 旧版兼容目录: MediaCrawler/data/weibo/csv/{note_id}/imgs/
        legacy_dir = base_dir / "imgs"
        
        for i, url in enumerate(urls):
            # 确定本地文件名规则
            if is_post:
                if len(urls) == 1:
                    img_name_stem = f"{current_id}"
                else:
                    img_name_stem = f"{current_id}_{i+1}"
            else:
                # 评论始终带序号 _1, _2...
                img_name_stem = f"{current_id}_{i+1}"
            
            # 处理后缀名
            ext = Path(url.split('?')[0]).suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                ext = ".jpg"
            
            img_name = f"{img_name_stem}{ext}"
            
            # 检查是否已存在（优先检查标准路径，其次检查旧版路径）
            save_path = base_dir / img_name
            legacy_path = legacy_dir / img_name
            
            target_path = None
            if save_path.exists():
                target_path = save_path
            elif legacy_path.exists():
                target_path = legacy_path
            else:
                # 都不存在，则执行下载到标准路径
                if self._download_image(url, save_path):
                    target_path = save_path
            
            if target_path:
                images.append(str(target_path.absolute()))
                
        return images

    def load_weibo_data(self, posts_file: str, comments_file: str) -> List[Dict[str, Any]]:
        """加载微博 CSV 数据并返回扁平化的项目列表。"""
        # 记录日期，用于后续对比
        date_str = Path(posts_file).stem.split('_')[-1]
        
        posts_df = pd.read_csv(posts_file, on_bad_lines='warn', engine='python', encoding='utf-8-sig')
        comments_df = pd.read_csv(comments_file, on_bad_lines='warn', engine='python', encoding='utf-8-sig')
        
        # 优化：按 note_id 对评论进行分组
        comments_by_post = {str(k): g for k, g in comments_df.groupby('note_id')}
        
        flat_items = []
        
        for _, post in posts_df.iterrows():
            note_id = str(post['note_id'])
            top_id = str(post.get('top_id', '')) 
            post_url = post.get('note_url', post.get('url', f"https://m.weibo.cn/detail/{note_id}"))
            
            # 1. 添加文章
            post_data = {
                "note_id": note_id,
                "comment_id": "0",
                "top_id": top_id,
                "url": post_url,
                "content": post.get('content', ''),
                "author": post.get('nickname', ''),
                "created_at": post.get('create_date_time', ''),
                "source": "weibo",
                "type": "post",
                "images": self._find_images("weibo", note_id, note_id, is_post=True, pictures_str=post.get('pictures', '')),
                "data_date": date_str # 记录数据日期
            }
            flat_items.append(post_data)
            
            # 2. 添加相关的评论
            if note_id in comments_by_post:
                for _, comment in comments_by_post[note_id].iterrows():
                    comment_id = str(comment['comment_id'])
                    flat_items.append({
                        "note_id": note_id,
                        "comment_id": comment_id,
                        "top_id": top_id,
                        "url": post_url,
                        "content": comment.get('content', ''),
                        "author": comment.get('nickname', ''),
                        "created_at": comment.get('create_date_time', ''),
                        "source": "weibo",
                        "type": "comment",
                        "images": self._find_images("weibo", note_id, comment_id, is_post=False, pictures_str=comment.get('pictures', '')),
                        "data_date": date_str
                    })
        
        return flat_items

    def compare_data(self, old_data: List[Dict[str, Any]], new_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """对比两份数据，检测新增、修改、删除。"""
        def get_key(item): return f"{item['note_id']}_{item['comment_id']}"
        
        old_map = {get_key(item): item for item in old_data}
        new_map = {get_key(item): item for item in new_data}
        
        added = []
        modified = []
        deleted = []
        
        for key, item in new_map.items():
            if key not in old_map:
                added.append(item)
            else:
                # 简单对比内容是否变化
                if item['content'] != old_map[key]['content']:
                    item['_old_content'] = old_map[key]['content']
                    modified.append(item)
                    
        for key, item in old_map.items():
            if key not in new_map:
                deleted.append(item)
                
        return {
            "added": added,
            "modified": modified,
            "deleted": deleted
        }

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
