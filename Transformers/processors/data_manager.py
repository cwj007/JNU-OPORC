import pandas as pd
import json
import os
import re
import httpx
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from ..config import MEDIA_CRAWLER_DATA_DIR, IMAGE_EXTENSIONS, CACHE_DIR

class DataManager:
    def __init__(self):
        self.data_dir = MEDIA_CRAWLER_DATA_DIR
        self._client = None
        self._client_lock = threading.Lock()

    def get_client(self):
        with self._client_lock:
            if self._client is None:
                # 缩短超时时间，避免单张图片下载卡死整个流程
                self._client = httpx.Client(follow_redirects=True, timeout=5.0)
            return self._client

    def __del__(self):
        if self._client:
            self._client.close()

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
            
        # 微博图片防盗链处理
        processed_url = url
        if "sinaimg.cn" in url:
            if "://" in url:
                clean_url = url.split("://", 1)[1]
            else:
                clean_url = url
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
            client = self.get_client()
            response = client.get(processed_url, headers=headers)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                return True
        except Exception as e:
            pass # 失败则跳过，不影响主流程
        return False

    def _find_images(self, platform: str, parent_note_id: str, current_id: str, is_post: bool, pictures_str: Optional[str]) -> List[str]:
        """
        根据最新的目录规则查找或下载图片：
        1. 文章图片：data/weibo/csv/{note_id}/imgs/{note_id}/{note_id}.jpg
        2. 评论图片：data/weibo/csv/{note_id}/imgs/{comment_id}/{comment_id}.jpg
        """
        if not pictures_str or pd.isna(pictures_str):
            return []
        
        # 解析 URL 列表
        urls = [u.strip() for u in str(pictures_str).split(',') if u.strip()]
        if not urls:
            return []
            
        images = []
        # 最新标准目录: MediaCrawler/data/weibo/csv/{parent_note_id}/imgs/{current_id}/
        base_dir = self.data_dir / platform / "csv" / parent_note_id / "imgs" / current_id
        
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

    def load_weibo_data(self, posts_file: str, comments_file: str, existing_ids: set = None) -> List[Dict[str, Any]]:
        """加载微博 CSV 数据并返回扁平化的项目列表。"""
        date_str = Path(posts_file).stem.split('_')[-1]
        
        posts_df = pd.read_csv(posts_file, on_bad_lines='warn', engine='python', encoding='utf-8-sig')
        comments_df = pd.read_csv(comments_file, on_bad_lines='warn', engine='python', encoding='utf-8-sig')
        
        # 预处理：确保 ID 是字符串
        posts_df['note_id'] = posts_df['note_id'].astype(str)
        posts_df = posts_df.where(pd.notnull(posts_df), None)
        
        comments_df['note_id'] = comments_df['note_id'].astype(str)
        comments_df['comment_id'] = comments_df['comment_id'].astype(str)
        comments_df = comments_df.where(pd.notnull(comments_df), None)

        # --- 核心优化：上下文缓存到磁盘 ---
        context_cache = {str(r['note_id']): r.get('content') for _, r in posts_df.iterrows() if r.get('content')}
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
        print(f"已同步 {len(context_cache)} 条文章上下文到磁盘缓存: {cache_file.name}")

        # 1. 处理文章数据 (CPU 并行)
        print(f"正在读取文章数据 (已处理过的 ID 将被自动跳过)...")
        
        # --- 核心优化：文章处理策略 ---
        # 建立无效文章 ID 集合，记录既无文本又无图片的文章 ID
        invalid_note_ids = set()
        # 线程安全锁，用于更新 invalid_note_ids
        invalid_ids_lock = threading.Lock()
        
        post_processed_count = 0
        def process_post(row_tuple):
            nonlocal post_processed_count
            idx, row = row_tuple
            note_id = str(row['note_id'])
            
            # --- 逻辑去重 (根据已存在文件) ---
            if existing_ids and f"{note_id}_0" in existing_ids:
                post_processed_count += 1
                return None
                
            content = row.get('content')
            # 确保内容不只是空白字符
            clean_content = str(content).strip() if content and not pd.isna(content) else ""
            
            pictures_str = row.get('pictures')
            
            # 优化：如果文字和图片配置同时为空，标记为无效并剔除
            if not clean_content and (not pictures_str or pd.isna(pictures_str)):
                with invalid_ids_lock:
                    invalid_note_ids.add(note_id)
                return None
            
            images = self._find_images("weibo", note_id, note_id, is_post=True, pictures_str=pictures_str)
            
            # 如果图片查找失败（物理文件不存在）且内容也为空，则无法分析，标记为无效并剔除
            if not clean_content and not images:
                with invalid_ids_lock:
                    invalid_note_ids.add(note_id)
                return None

            return {
                "note_id": note_id,
                "comment_id": "0",
                "top_id": str(row.get('top_id')) if row.get('top_id') else None,
                "url": row.get('note_url', row.get('url', f"https://m.weibo.cn/detail/{note_id}")),
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

        posts_list = [None] * len(posts_df)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_post, (idx, row)): idx for idx, row in posts_df.iterrows()}
            for future in futures:
                idx = futures[future]
                res = future.result()
                posts_list[idx] = res
        
        # 过滤掉 None (被跳过或无效的数据)，同时保持原始 CSV 顺序
        posts_list = [p for p in posts_list if p is not None]

        if post_processed_count > 0:
            print(f"  - 文章表已跳过 {post_processed_count} 条已处理记录。")

        # 2. 处理评论数据 (CPU 并行)
        total_raw_comments = len(comments_df)
        print(f"正在读取 {total_raw_comments} 条评论数据...")
        
        comment_processed_count = 0
        
        # 构建文章内容缓存，确保即使是纯图片文章也能提供背景提示，而不是空字符串
        full_posts_content_cache = {}
        for _, r in posts_df.iterrows():
            nid = str(r['note_id'])
            c = r.get('content')
            clean_c = str(c).strip() if c and not pd.isna(c) else ""
            if not clean_c:
                # 如果没有文字，检查是否有图片配置
                pics = r.get('pictures')
                if pics and not pd.isna(pics):
                    full_posts_content_cache[nid] = "[图片内容]"
                else:
                    full_posts_content_cache[nid] = ""
            else:
                full_posts_content_cache[nid] = clean_c

        # 构建当前批次所有评论的内容映射，用于对话链上下文溯源
        full_comments_content_cache = {str(row['comment_id']): row.get('content') for _, row in comments_df.iterrows()}
        
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
            
            # 优化：如果所属文章是无效文章（无图无文），则直接剔除评论训练
            if note_id in invalid_note_ids:
                return None

            # --- 逻辑去重 (根据已存在文件) ---
            if existing_ids and f"{note_id}_{comment_id}" in existing_ids:
                comment_processed_count += 1
                return None
                
            content = row.get('content')
            # 确保内容不只是空白字符
            clean_content = str(content).strip() if content and not pd.isna(content) else ""
            
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
            if not clean_content and (not pictures_str or pd.isna(pictures_str)):
                return None
            
            comment_images = self._find_images("weibo", note_id, comment_id, is_post=False, pictures_str=pictures_str)
            
            # 如果图片查找失败（物理文件不存在）且内容也为空，直接剔除
            if not clean_content and not comment_images:
                return None
            
            parent_content = full_posts_content_cache.get(note_id, "")
            
            # 顶级评论的 parent_comment_id 与其 comment_id 相同
            raw_parent_id = row.get('parent_comment_id')
            parent_comment_id = str(raw_parent_id) if raw_parent_id and not pd.isna(raw_parent_id) else comment_id
            
            # 优化 2：评论的字段有一个 sub_comment_count 子评论数量，
            # 如果这个子评论数不大于 0 则表示没有子评论数据。就不需要缓存处理。
            sub_comment_count = int(row.get('sub_comment_count', 0))
            
            # 获取对话链上下文：如果不是顶级评论，则获取父评论内容
            reply_to_content = ""
            if parent_comment_id != comment_id:
                # 只有当父评论确实存在于缓存中时才提取
                reply_to_content = full_comments_content_cache.get(parent_comment_id, "")

            return {
                "note_id": note_id,
                "comment_id": comment_id,
                "top_id": None,
                "url": row.get('url', f"https://m.weibo.cn/detail/{note_id}"),
                "content": clean_content or "[图片评论]", # 纯图片评论占位符
                "author": row.get('nickname'),
                "created_at": row.get('create_date_time'),
                "source": "weibo",
                "type": "comment",
                "images": comment_images,
                "data_date": date_str,
                "parent_content": parent_content,      # 文章内容
                "reply_to_content": reply_to_content,  # 父评论内容（对话链上下文）
                "comment_like_count": row.get('liked_count', 0), # 统一命名为 comment_like_count
                "sub_comment_count": sub_comment_count,
                "ip_location": row.get('ip_location', ''),
                "gender": row.get('gender', ''),
                "parent_comment_id": parent_comment_id
            }

        # 使用固定长度列表并按索引填入，以确保并行处理后依然维持 CSV 原始顺序
        comments_list = [None] * len(comments_df)
        with ThreadPoolExecutor(max_workers=10) as executor:
            # 显式传递 idx
            futures = {executor.submit(process_row, (idx, row)): idx for idx, row in comments_df.iterrows()}
            for future in futures:
                idx = futures[future]
                res = future.result()
                comments_list[idx] = res
        
        # 合并文章和评论，同时保持各自内部的原始顺序
        final_list = posts_list + [c for c in comments_list if c is not None]
        
        if comment_processed_count > 0:
            print(f"  - 评论表已跳过 {comment_processed_count} 条已处理记录。")
            
        print(f"加载完成: 过滤后剩余 {len(final_list)} 条新数据待处理 (已跳过 {len(comments_df) + len(posts_df) - len(final_list)} 条重复或无效数据)")
        return final_list

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
