import pandas as pd
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from ..config import MEDIA_CRAWLER_DATA_DIR, IMAGE_EXTENSIONS, CACHE_DIR
from Transformers import utils
from Transformers.processors.data_loader import WeiboCSVLoader, WeiboSQLiteLoader, ZhihuSQLiteLoader, ZhihuJSONLoader, WeiboJSONLoader, ZhihuCSVLoader

class DataManager:
    def __init__(self):
        self.data_dir = MEDIA_CRAWLER_DATA_DIR
        
        # Loaders
        self.weibo_csv_loader = WeiboCSVLoader()
        self.weibo_sqlite_loader = WeiboSQLiteLoader()
        self.zhihu_loader = ZhihuSQLiteLoader()
        self.zhihu_json_loader = ZhihuJSONLoader()
        self.zhihu_csv_loader = ZhihuCSVLoader()
        self.weibo_json_loader = WeiboJSONLoader()

    def detect_platform(self, file_path: str) -> str:
        """Identify platform (weibo/zhihu) based on file path."""
        path_str = str(file_path).lower()
        if "weibo" in path_str:
            return "weibo"
        elif "zhihu" in path_str:
            return "zhihu"
        return "unknown"

    def _find_images(self, platform: str, parent_note_id: str, current_id: str, is_post: bool, pictures_str: Optional[str], source_type: str = "csv") -> List[str]:
        """
        根据最新的目录规则查找或下载图片：
        1. 文章图片：data/weibo/{source_type}/{note_id}/imgs/{note_id}/{note_id}.jpg
        2. 评论图片：data/weibo/{source_type}/{note_id}/imgs/{comment_id}/{comment_id}.jpg
        """
        if not pictures_str or pd.isna(pictures_str):
            return []
        
        # 解析 URL 列表
        urls = [u.strip() for u in str(pictures_str).split(',') if u.strip()]
        if not urls:
            return []
            
        images = []
        # 最新标准目录: MediaCrawler/data/weibo/{source_type}/{parent_note_id}/imgs/{current_id}/
        base_dir = self.data_dir / platform / source_type / parent_note_id / "imgs" / current_id
        
        for i, url in enumerate(urls):
            # 确定本地文件名规则
            if len(urls) == 1:
                img_name_stem = f"{current_id}"
            else:
                img_name_stem = f"{current_id}_{i+1}"
            
            # 处理后缀名（优先使用 .jpg）
            ext = ".jpg"
            img_name = f"{img_name_stem}{ext}"
            save_path = base_dir / img_name
            
            # 必须进行校验，如果文件不存在，则不加入列表，防止 VLM 推理时报错
            if save_path.exists():
                images.append(str(save_path.absolute()))
            else:
                # 尝试其他可能的后缀 (png, jpeg)
                for alt_ext in [".png", ".jpeg", ".JPG"]:
                    alt_path = base_dir / f"{img_name_stem}{alt_ext}"
                    if alt_path.exists():
                        images.append(str(alt_path.absolute()))
                        break
                
        return images

    def load_weibo_data(self, posts_file: str = None, comments_file: str = None, 
                       source_type: str = "csv", date: str = None, 
                       json_file: str = None,
                       existing_ids: set = None) -> List[Dict[str, Any]]:
        """
        加载微博数据并返回扁平化的项目列表。
        支持 CSV (默认), SQLite 和 JSON 数据源。
        """
        posts_data = []
        comments_data = []
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # 1. Load Data
        if source_type == "csv":
            if not posts_file or not comments_file:
                raise ValueError("CSV source requires posts_file and comments_file")
            
            date_str = Path(posts_file).stem.split('_')[-1]
            posts_data, comments_data = self.weibo_csv_loader.load_data(posts_file, comments_file)
            
        elif source_type == "sqlite":
            if date:
                date_str = date
            posts_data, comments_data = self.weibo_sqlite_loader.load_data(date=date)
            
        elif source_type == "json":
            if not json_file:
                 raise ValueError("JSON source requires json_file path (can be file or directory)")
            posts_data, comments_data = self.weibo_json_loader.load_data(json_file)
            if not date:
                try:
                    date_str = Path(json_file).stem
                except:
                    pass
            
        else:
            raise ValueError(f"Unsupported source_type: {source_type}")

        # --- 核心优化：上下文缓存到磁盘 ---
        # Note: In dicts, keys are strings
        context_cache = {str(r['note_id']): r.get('content') for r in posts_data if r.get('content')}
        cache_file = CACHE_DIR / "context_cache.json"
        
        # 合并旧缓存（如果有）
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    old_cache = json.load(f)
                    old_cache.update(context_cache)
                    context_cache = old_cache
            except: pass
            
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(context_cache, f, ensure_ascii=False, indent=2)
        utils.logger.info(f"[DataManager.load_weibo_data] 已同步 {len(context_cache)} 条文章上下文到磁盘缓存: {cache_file.name}")

        # 1. 处理文章数据 (CPU 并行)
        utils.logger.info(f"[DataManager.load_weibo_data] 正在读取文章数据 (已处理过的 ID 将被自动跳过)...")
        
        # --- 核心优化：文章处理策略 ---
        # 建立无效文章 ID 集合，记录既无文本又无图片的文章 ID
        invalid_note_ids = set()
        # 线程安全锁，用于更新 invalid_note_ids 和 seen_ids_this_run
        data_lock = threading.Lock()
        seen_ids_this_run = set()
        
        post_processed_count = 0
        def process_post(row_tuple):
            nonlocal post_processed_count
            idx, row = row_tuple
            note_id = str(row['note_id'])
            full_id = f"{note_id}_0"
            
            # --- 逻辑去重 (根据已存在文件或本轮已处理) ---
            if (existing_ids and full_id in existing_ids) or (full_id in seen_ids_this_run):
                post_processed_count += 1
                return None
            
            with data_lock:
                if full_id in seen_ids_this_run:
                    post_processed_count += 1
                    return None
                seen_ids_this_run.add(full_id)
                
            content = row.get('content')
            # 确保内容不只是空白字符
            clean_content = str(content).strip() if content else ""
            
            pictures_str = row.get('pictures')
            
            # 优化：如果文字和图片配置同时为空，标记为无效并剔除
            if not clean_content and not pictures_str:
                with data_lock:
                    invalid_note_ids.add(note_id)
                return None
            
            images = self._find_images("weibo", note_id, note_id, is_post=True, pictures_str=pictures_str, source_type=source_type)
            
            # 如果图片查找失败（物理文件不存在）且内容也为空，则无法分析，标记为无效并剔除
            if not clean_content and not images:
                with data_lock:
                    invalid_note_ids.add(note_id)
                return None

            return {
                "note_id": note_id,
                "comment_id": "0",
                "top_id": str(row.get('top_id')) if row.get('top_id') else None,
                "url": row.get('note_url') or row.get('url') or f"https://m.weibo.cn/detail/{note_id}",
                "content": clean_content or "[图片内容]", # 为纯图片提供占位符
                "author": row.get('nickname'),
                "created_at": row.get('create_date_time'),
                "source": "weibo",
                "type": "post",
                "images": images,
                "data_date": date_str,
                "liked_count": row.get('liked_count', 0),
                "comments_count": row.get('comments_count', 0),
                "shared_count": row.get('shared_count', 0),
                "ip_location": row.get('ip_location', '')
            }

        posts_list = [None] * len(posts_data)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_post, (idx, row)): idx for idx, row in enumerate(posts_data)}
            for future in futures:
                idx = futures[future]
                res = future.result()
                posts_list[idx] = res
        
        # 过滤掉 None (被跳过或无效的数据)，同时保持原始顺序
        posts_list = [p for p in posts_list if p is not None]

        if post_processed_count > 0:
            utils.logger.info(f"[DataManager.load_weibo_data] 文章表已跳过 {post_processed_count} 条已处理记录。")

        # 2. 处理评论数据 (CPU 并行)
        total_raw_comments = len(comments_data)
        utils.logger.info(f"[DataManager.load_weibo_data] 正在读取 {total_raw_comments} 条评论数据...")
        
        comment_processed_count = 0
        
        # 构建文章内容缓存，确保即使是纯图片文章也能提供背景提示，而不是空字符串
        full_posts_content_cache = {}
        for r in posts_data:
            nid = str(r['note_id'])
            c = r.get('content')
            clean_c = str(c).strip() if c else ""
            if not clean_c:
                # 如果没有文字，检查是否有图片配置
                pics = r.get('pictures')
                if pics:
                    full_posts_content_cache[nid] = "[图片内容]"
                else:
                    full_posts_content_cache[nid] = ""
            else:
                full_posts_content_cache[nid] = clean_c

        # 构建当前批次所有评论的内容映射，用于对话链上下文溯源
        full_comments_content_cache = {str(row['comment_id']): row.get('content') for row in comments_data}
        
        # 垃圾评论关键词过滤
        spam_keywords = ["扫码", "加群", "无门槛", "网页链接", "投票", "点击链接", "免费领取", "私聊", "看我主页"]
        # 直接剔除纯图片评论提示语 (这些数据没有实际文本价值)
        image_comment_placeholders = ["图片评论", "评论配图"]
        
        # 预编译正则，识别重复字符（如：啊啊啊啊啊啊）或无意义字符
        nonsense_pattern = re.compile(r'(.)\1{10,}') 

        def process_row(row_tuple):
            nonlocal comment_processed_count
            idx, row = row_tuple
            note_id = str(row['note_id'])
            comment_id = str(row['comment_id'])
            full_id = f"{note_id}_{comment_id}"
            
            # 优化：如果所属文章是无效文章（无图无文），则直接剔除评论训练
            if note_id in invalid_note_ids:
                return None

            # --- 逻辑去重 (根据已存在文件或本轮已处理) ---
            if (existing_ids and full_id in existing_ids) or (full_id in seen_ids_this_run):
                comment_processed_count += 1
                return None
            
            with data_lock:
                if full_id in seen_ids_this_run:
                    comment_processed_count += 1
                    return None
                seen_ids_this_run.add(full_id)
                
            content = row.get('content')
            # 确保内容不只是空白字符
            clean_content = str(content).strip() if content else ""
            
            # --- 核心优化：垃圾评论/无意义评论过滤 ---
            if clean_content:
                # 1. 关键词过滤
                if any(kw in clean_content for kw in spam_keywords):
                    return None
                # 2. 占位符过滤
                if clean_content in image_comment_placeholders:
                    clean_content = "" # 转化为纯图片逻辑处理
                # 3. 重复字符过滤
                if nonsense_pattern.search(clean_content):
                    return None
                # 4. 太短且无图片（如只有1个字或纯符号）
                if len(clean_content) < 2 and not row.get('pictures'):
                    return None
            
            pictures_str = row.get('pictures')
            
            # 如果文字和图片配置同时为空，直接剔除
            if not clean_content and not pictures_str:
                return None
            
            comment_images = self._find_images("weibo", note_id, comment_id, is_post=False, pictures_str=pictures_str, source_type=source_type)
            
            # 如果图片查找失败（物理文件不存在）且内容也为空，直接剔除
            if not clean_content and not comment_images:
                return None
            
            parent_content = full_posts_content_cache.get(note_id, "")
            
            # 顶级评论的 parent_comment_id 与其 comment_id 相同
            raw_parent_id = row.get('parent_comment_id')
            parent_comment_id = str(raw_parent_id) if raw_parent_id else comment_id
            
            # 优化 2：评论的字段有一个 sub_comment_count 子评论数量，
            # 如果这个子评论数不大于 0 则表示没有子评论数据。就不需要缓存处理。
            sub_comment_count = int(row.get('sub_comment_count') or 0)
            
            # 获取对话链上下文：如果不是顶级评论，则获取父评论内容
            reply_to_content = ""
            if parent_comment_id != comment_id:
                # 只有当父评论确实存在于缓存中时才提取
                reply_to_content = full_comments_content_cache.get(parent_comment_id, "")

            return {
                "note_id": note_id,
                "comment_id": comment_id,
                "top_id": None,
                "url": row.get('url') or f"https://m.weibo.cn/detail/{note_id}",
                "content": clean_content or "[图片评论]", # 纯图片评论占位符
                "author": row.get('nickname'),
                "created_at": row.get('create_date_time'),
                "source": "weibo",
                "type": "comment",
                "images": comment_images,
                "data_date": date_str,
                "parent_content": parent_content,      # 文章内容
                "reply_to_content": reply_to_content,  # 父评论内容（对话链上下文）
                "comment_like_count": row.get('comment_like_count') or row.get('liked_count', 0), # 统一命名为 comment_like_count
                "sub_comment_count": sub_comment_count,
                "ip_location": row.get('ip_location', ''),
                "gender": row.get('gender', ''),
                "parent_comment_id": parent_comment_id
            }

        # 使用固定长度列表并按索引填入，以确保并行处理后依然维持原始顺序
        comments_list = [None] * len(comments_data)
        with ThreadPoolExecutor(max_workers=10) as executor:
            # 显式传递 idx
            futures = {executor.submit(process_row, (idx, row)): idx for idx, row in enumerate(comments_data)}
            for future in futures:
                idx = futures[future]
                res = future.result()
                comments_list[idx] = res
        
        # 合并文章和评论，同时保持各自内部的原始顺序
        final_list = posts_list + [c for c in comments_list if c is not None]
        
        # 增加详细日志输出，展示加载的数据样本
        if final_list:
            sample_count = min(3, len(final_list))
            utils.logger.info(f"[DataManager.load_weibo_data] DEBUG: 成功加载 {len(final_list)} 条数据。前 {sample_count} 条样本:")
            for i in range(sample_count):
                item = final_list[i]
                utils.logger.info(f"[DataManager.load_weibo_data] 样本: [{item.get('type')}] ID: {item.get('note_id')}_{item.get('comment_id')} | Content: {item.get('content')[:50]}...")
        
        if comment_processed_count > 0:
            utils.logger.info(f"[DataManager.load_weibo_data] 评论表已跳过 {comment_processed_count} 条已处理记录。")
            
        utils.logger.info(f"[DataManager.load_weibo_data] 加载完成: 过滤后剩余 {len(final_list)} 条新数据待处理 (已跳过 {len(comments_data) + len(posts_data) - len(final_list)} 条重复或无效数据)")
        return final_list

    def load_zhihu_data(self, posts_file: str = None, comments_file: str = None, 
                       source_type: str = "csv", date: str = None, 
                       json_file: str = None,
                       existing_ids: set = None) -> List[Dict[str, Any]]:
        """
        加载知乎数据并返回扁平化的项目列表。
        支持 CSV, SQLite 和 JSON 数据源。
        """
        posts_data = []
        comments_data = []
        date_str = date if date else datetime.now().strftime("%Y-%m-%d")
        
        # 1. Load Data
        if source_type == "csv":
            if not posts_file:
                 raise ValueError("CSV source requires posts_file")
            
            try:
                date_str = Path(posts_file).stem.split('_')[-1]
            except:
                pass
                
            posts_data, comments_data = self.zhihu_csv_loader.load_data(posts_file, comments_file)
            
            # Map CSV fields to standard internal structure
            new_posts = []
            for p in posts_data:
                # Handle timestamp conversion if needed
                create_time = p.get('created_time', '')
                if isinstance(create_time, (int, float)):
                    try:
                        create_time = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d %H:%M:%S")
                    except: pass
                
                new_p = {
                    "note_id": str(p.get('content_id', p.get('id', ''))),
                    "user_id": str(p.get('user_id', '')),
                    "nickname": p.get('user_nickname', ''),
                    "avatar": p.get('user_avatar', ''),
                    "title": p.get('title', ''),
                    "content": p.get('content_text', ''),
                    "desc": p.get('desc', ''),
                    "note_url": p.get('content_url', ''),
                    "create_date_time": str(create_time),
                    "liked_count": p.get('voteup_count', 0),
                    "comments_count": p.get('comment_count', 0),
                    "question_id": p.get('question_id', ''),
                    "type": p.get('content_type', 'article'),
                    "ip_location": None # Not in article struct provided
                }
                new_posts.append(new_p)
            posts_data = new_posts
            
            new_comments = []
            for c in comments_data:
                # Handle timestamp conversion
                publish_time = c.get('publish_time', '')
                if isinstance(publish_time, (int, float)):
                    try:
                        publish_time = datetime.fromtimestamp(publish_time).strftime("%Y-%m-%d %H:%M:%S")
                    except: pass

                new_c = {
                    "comment_id": str(c.get('comment_id', c.get('id', ''))),
                    "note_id": str(c.get('content_id', '')),
                    "parent_comment_id": str(c.get('parent_comment_id', '')),
                    "content": c.get('content', ''),
                    "nickname": c.get('user_nickname', ''),
                    "avatar": c.get('user_avatar', ''),
                    "create_date_time": str(publish_time),
                    "liked_count": c.get('like_count', 0),
                    "sub_comment_count": c.get('sub_comment_count', 0),
                    "ip_location": c.get('ip_location', '')
                }
                new_comments.append(new_c)
            comments_data = new_comments

        elif source_type == "sqlite":
             if date:
                 date_str = date
             posts_data, comments_data = self.zhihu_loader.load_data(date=date)
             
        elif source_type == "json":
             if not json_file:
                 raise ValueError("JSON source requires json_file path")
             posts_data, comments_data = self.zhihu_json_loader.load_data(json_file)
             if not date:
                 try:
                     date_str = Path(json_file).stem
                 except:
                     pass
                     
        else:
             raise ValueError(f"Unsupported source_type: {source_type}")

        # --- Context Caching ---
        context_cache = {str(r.get('note_id', '')): r.get('content', '') for r in posts_data if r.get('content')}
        cache_file = CACHE_DIR / "zhihu_context_cache.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    old_cache = json.load(f)
                    old_cache.update(context_cache)
                    context_cache = old_cache
            except: pass
            
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(context_cache, f, ensure_ascii=False, indent=2)
        utils.logger.info(f"[DataManager.load_zhihu_data] Synced {len(context_cache)} articles context to cache: {cache_file.name}")

        # 1. Process Posts
        utils.logger.info(f"[DataManager.load_zhihu_data] Processing posts...")
        
        post_processed_count = 0
        data_lock = threading.Lock()
        seen_ids_this_run = set()

        def process_post(row_tuple):
            nonlocal post_processed_count
            idx, row = row_tuple
            note_id = str(row['note_id'])
            full_id = f"{note_id}_0"
            
            # --- 逻辑去重 (根据已存在文件或本轮已处理) ---
            if (existing_ids and full_id in existing_ids) or (full_id in seen_ids_this_run):
                post_processed_count += 1
                return None
            
            with data_lock:
                if full_id in seen_ids_this_run:
                    post_processed_count += 1
                    return None
                seen_ids_this_run.add(full_id)
                
            content = row.get('content')
            title = row.get('title', '')
            clean_content = str(content).strip() if content else ""
            
            # Combine title and content
            full_content = f"{title}\n{clean_content}".strip()
            
            if not full_content:
                return None
            
            return {
                "note_id": note_id,
                "comment_id": "0",
                "top_id": None,
                "url": row.get('note_url') or "",
                "content": full_content,
                "author": row.get('nickname'),
                "created_at": row.get('create_date_time'),
                "source": "zhihu",
                "type": "post",
                "images": [],
                "data_date": date_str,
                "liked_count": row.get('liked_count', 0),
                "comments_count": row.get('comments_count', 0),
                "shared_count": 0,
                "ip_location": row.get('ip_location', '')
            }

        posts_list = [None] * len(posts_data)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_post, (idx, row)): idx for idx, row in enumerate(posts_data)}
            for future in futures:
                idx = futures[future]
                res = future.result()
                posts_list[idx] = res
        
        posts_list = [p for p in posts_list if p is not None]

        if post_processed_count > 0:
            utils.logger.info(f"[DataManager.load_zhihu_data] Skipped {post_processed_count} processed posts.")

        # 2. Process Comments
        utils.logger.info(f"[DataManager.load_zhihu_data] Processing {len(comments_data)} comments...")
        
        comment_processed_count = 0
        
        # Build context caches
        full_posts_content_cache = {}
        for r in posts_data:
            nid = str(r['note_id'])
            c = r.get('content')
            t = r.get('title', '')
            clean_c = f"{t}\n{c}".strip()
            full_posts_content_cache[nid] = clean_c

        full_comments_content_cache = {str(row['comment_id']): row.get('content') for row in comments_data}
        
        spam_keywords = ["扫码", "加群", "无门槛", "网页链接", "投票", "点击链接", "免费领取", "私聊", "看我主页"]
        nonsense_pattern = re.compile(r'(.)\1{10,}') 

        def process_comment(row_tuple):
            nonlocal comment_processed_count
            idx, row = row_tuple
            note_id = str(row['note_id'])
            comment_id = str(row['comment_id'])
            full_id = f"{note_id}_{comment_id}"
            
            # --- 逻辑去重 (根据已存在文件或本轮已处理) ---
            if (existing_ids and full_id in existing_ids) or (full_id in seen_ids_this_run):
                comment_processed_count += 1
                return None
            
            with data_lock:
                if full_id in seen_ids_this_run:
                    comment_processed_count += 1
                    return None
                seen_ids_this_run.add(full_id)
                
            content = row.get('content')
            clean_content = str(content).strip() if content else ""
            
            if clean_content:
                if any(kw in clean_content for kw in spam_keywords):
                    return None
                if nonsense_pattern.search(clean_content):
                    return None
                if len(clean_content) < 2:
                    return None
            else:
                return None
            
            parent_content = full_posts_content_cache.get(note_id, "")
            
            raw_parent_id = row.get('parent_comment_id')
            # Handle empty or '0' parent id
            if raw_parent_id in [None, '', '0', 0]:
                parent_comment_id = comment_id
            else:
                parent_comment_id = str(raw_parent_id)

            reply_to_content = ""
            if parent_comment_id != comment_id:
                reply_to_content = full_comments_content_cache.get(parent_comment_id, "")

            return {
                "note_id": note_id,
                "comment_id": comment_id,
                "top_id": None,
                "url": "",
                "content": clean_content,
                "author": row.get('nickname'),
                "created_at": row.get('create_date_time'),
                "source": "zhihu",
                "type": "comment",
                "images": [],
                "data_date": date_str,
                "parent_content": parent_content,
                "reply_to_content": reply_to_content,
                "comment_like_count": row.get('liked_count', 0),
                "sub_comment_count": row.get('sub_comment_count', 0),
                "ip_location": row.get('ip_location', ''),
                "gender": "", # Zhihu struct doesn't have gender in comment
                "parent_comment_id": parent_comment_id
            }

        comments_list = [None] * len(comments_data)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_comment, (idx, row)): idx for idx, row in enumerate(comments_data)}
            for future in futures:
                idx = futures[future]
                res = future.result()
                comments_list[idx] = res
        
        final_list = posts_list + [c for c in comments_list if c is not None]
        
        if comment_processed_count > 0:
            utils.logger.info(f"[DataManager.load_zhihu_data] Skipped {comment_processed_count} processed comments.")
            
        utils.logger.info(f"[DataManager.load_zhihu_data] Loaded {len(final_list)} items.")
        return final_list



    def load_data(self, platform: str = None, source_type: str = "sqlite", **kwargs) -> List[Dict[str, Any]]:
        """
        Unified data loading method.
        If platform is specified ('weibo' or 'zhihu'), loads data for that platform.
        If platform is None, loads data for BOTH platforms and combines them.
        Default source_type is 'sqlite'.
        """
        all_data = []
        
        # Auto-detect platform from file path if not specified
        if not platform and source_type in ['json', 'csv']:
            file_path = kwargs.get('json_file') or kwargs.get('posts_file')
            if file_path:
                detected = self.detect_platform(file_path)
                if detected != 'unknown':
                    platform = detected
                    utils.logger.info(f"[DataManager.load_data] Auto-detected platform '{platform}' from file path.")

        platforms_to_load = []
        if platform:
            if platform.lower() == 'weibo':
                platforms_to_load.append('weibo')
            elif platform.lower() == 'zhihu':
                platforms_to_load.append('zhihu')
            else:
                utils.logger.warning(f"[DataManager.load_data] Unknown platform '{platform}', defaulting to ALL.")
                platforms_to_load = ['weibo', 'zhihu']
        else:
            platforms_to_load = ['weibo', 'zhihu']
            
        for p in platforms_to_load:
            utils.logger.info(f"[DataManager.load_data] Loading data for platform: {p} (source={source_type})")
            try:
                if p == 'weibo':
                    data = self.load_weibo_data(source_type=source_type, **kwargs)
                    all_data.extend(data)
                elif p == 'zhihu':
                    data = self.load_zhihu_data(source_type=source_type, **kwargs)
                    all_data.extend(data)
            except Exception as e:
                utils.logger.error(f"[DataManager.load_data] Error loading {p} data: {e}")
                
        return all_data

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

    def load_json_data(self, json_file: str, existing_ids: set = None) -> List[Dict[str, Any]]:
        """Load unlabelled JSON data for batch processing."""
        with open(json_file, 'r', encoding='utf-8') as f:
            try:
                # 尝试加载为标准 JSON 数组
                data = json.load(f)
            except json.JSONDecodeError:
                # 如果失败，尝试按行加载 JSONL
                f.seek(0)
                data = [json.loads(line) for line in f if line.strip()]
        
        # --- 提前去重检查 ---
        if existing_ids:
            filtered_data = []
            for item in data:
                note_id = str(item.get('note_id', ''))
                comment_id = str(item.get('comment_id', '0'))
                if f"{note_id}_{comment_id}" not in existing_ids:
                    filtered_data.append(item)
            return filtered_data
            
        return data
