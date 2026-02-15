import json
import re
import threading
import sys
import time
import queue
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..models.vlm_handler import VLMHandler
import concurrent.futures
from ..config import (
    ANALYSIS_PROMPT, MAX_IMAGES_FOR_VLM, SENTIMENT_CATEGORIES, 
    FINE_GRAINED_SENTIMENT_CATEGORIES, INTENT_CATEGORIES, 
    MEDIA_CRAWLER_DATA_DIR, FINE_GRAINED_SENTIMENT_MAPPING, 
    INTENT_CATEGORIES_MAPPING, TRANSFORMERS_DIR, CACHE_DIR
)
from Transformers import utils

class MultimodalAnalyzer:
    def __init__(self, vlm_handler: VLMHandler):
        self.vlm = vlm_handler
        self._analysis_cache = {} # 全量缓存: signature -> analysis
        self._vision_cache = {}   # 视觉特征缓存: img_md5 -> {objects, ocr_text}
        self._text_pool = {}      # 语义池: text -> analysis (用于相似度匹配)
        self._post_context_cache = {} # 文章分析结果缓存: note_id -> analysis (用于评论上下文)
        self._load_persistent_cache()
        self.adaptive_batch_size = None # 动态调整的批大小
        self.prefetch_queue = queue.Queue(maxsize=5) 
        self.postprocess_queue = queue.Queue(maxsize=10) # 新增：后处理队列
        self.cpu_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8) # 增加 worker 数量利用 CPU 空闲

    def _load_persistent_cache(self):
        """从磁盘加载持久化缓存（如果存在）。"""
        cache_path = CACHE_DIR / "analysis_cache.json"
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._analysis_cache = data.get("analysis", {})
                    self._vision_cache = data.get("vision", {})
                    self._text_pool = data.get("text_pool", {})
                utils.logger.info(f"[MultimodalAnalyzer._load_persistent_cache] 已加载持久化缓存: {len(self._analysis_cache)} 条记录, {len(self._text_pool)} 条语义记录")
            except json.JSONDecodeError as e:
                utils.logger.error(f"[MultimodalAnalyzer._load_persistent_cache] 缓存文件损坏: {e}")
                # 备份损坏的文件
                backup_path = cache_path.with_suffix(f".json.bak.{int(time.time())}")
                try:
                    cache_path.rename(backup_path)
                    utils.logger.warning(f"[MultimodalAnalyzer._load_persistent_cache] 已将损坏的缓存文件备份为: {backup_path.name}，并将使用空缓存启动。")
                except Exception as backup_error:
                     utils.logger.error(f"[MultimodalAnalyzer._load_persistent_cache] 备份损坏文件失败: {backup_error}")
            except Exception as e:
                utils.logger.error(f"[MultimodalAnalyzer._load_persistent_cache] 加载失败: {e}")

    def _save_persistent_cache(self):
        """将缓存保存到磁盘。"""
        cache_path = CACHE_DIR / "analysis_cache.json"
        temp_path = cache_path.with_suffix(".tmp")
        try:
            # 限制语义池大小，防止无限增长
            if len(self._text_pool) > 5000:
                # 简单删除前一半
                keys = list(self._text_pool.keys())
                self._text_pool = {k: self._text_pool[k] for k in keys[2500:]}

            # 先写入临时文件，确保写入原子性，防止文件损坏
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "analysis": self._analysis_cache,
                    "vision": self._vision_cache,
                    "text_pool": self._text_pool
                }, f, ensure_ascii=False, indent=2)
            
            # 写入成功后替换原文件
            if temp_path.exists():
                temp_path.replace(cache_path)
                
        except Exception as e:
            utils.logger.error(f"[MultimodalAnalyzer._save_persistent_cache] 保存失败: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except:
                    pass

    def _check_fast_path(self, text: str) -> Optional[Dict[str, Any]]:
        """快速判定短文本或无意义回复（1ms 级）。"""
        t = text.strip()
        if not t: return None
        
        # 1. 极短文本 (1-3个字) 且多为语气词/表情
        if len(t) <= 3:
            # 特殊情况：数字 "1" 或 "11" 表示赞同
            if re.match(r'^1+$', t):
                return {
                    "sentiment": "正面", "fine_grained_sentiment": "赞赏",
                    "intent": "推荐/安利", "irony_detected": False,
                    "reasoning": "数字 '1' 表达赞同/附议。",
                    "visual_objects": [], "ocr_text": ""
                }
            
            # 特殊情况：常用语义表情
            emoji_mapping = {
                "🙏": ("正面", "赞赏", "推荐/安利", "祈祷/感谢"),
                "👍": ("正面", "赞赏", "推荐/安利", "点赞"),
                "❤️": ("正面", "愉快", "分享/展示", "喜爱"),
                "🌹": ("正面", "愉快", "分享/展示", "送花/好评"),
                "👏": ("正面", "愉快", "分享/展示", "鼓掌"),
            }
            if t in emoji_mapping:
                s, fg, it, res = emoji_mapping[t]
                return {
                    "sentiment": s, "fine_grained_sentiment": fg,
                    "intent": it, "irony_detected": False,
                    "reasoning": f"纯表情回复：{res}。",
                    "visual_objects": [], "ocr_text": ""
                }

            # 语气词、纯标点、纯数字、简单表情占位符 [xxx]
            if re.match(r'^[\u4e00-\u9fa5]{1,3}$', t):
                # 判定是否为常见无意义词
                if t in ["哈哈哈", "哈", "呵呵", "嘿嘿", "码住", "滴滴", "打卡", "蹲蹲", "围观"]:
                    return {
                        "sentiment": "中性", "fine_grained_sentiment": "中立",
                        "intent": "吃瓜/围观", "irony_detected": False,
                        "reasoning": "短回复，判定为围观/中性。",
                        "visual_objects": [], "ocr_text": ""
                    }
                if t in ["真棒", "好棒", "太牛", "牛逼", "给力", "赞", "好"]:
                    return {
                        "sentiment": "正面", "fine_grained_sentiment": "赞赏",
                        "intent": "分享/展示", "irony_detected": False,
                        "reasoning": "短好评回复。",
                        "visual_objects": [], "ocr_text": ""
                    }
            
            if re.match(r'^[0-9a-zA-Z\s\W]+$', t) or (t.startswith("[") and t.endswith("]")):
                 return {
                    "sentiment": "中性", "fine_grained_sentiment": "中立",
                    "intent": "其他", "irony_detected": False,
                    "reasoning": "纯表情或纯符号回复。",
                    "visual_objects": [], "ocr_text": ""
                }
        
        # 2. 重复字符 (如: "666666", "加油加油加油")
        if len(set(t)) <= 2 and len(t) > 3:
            return {
                "sentiment": "正面" if any(c in "赞好强牛6" for c in t) else "中性",
                "fine_grained_sentiment": "赞赏" if any(c in "赞好强牛6" for c in t) else "中立",
                "intent": "其他", "irony_detected": False,
                "reasoning": "重复字符回复。",
                "visual_objects": [], "ocr_text": ""
            }
            
        return None

    def _check_semantic_similarity(self, text: str) -> Optional[Dict[str, Any]]:
        """简单的语义相似度检查（字符级 Jaccard 相似度）。"""
        if not text or len(text) < 4: return None
        
        t_set = set(text)
        t_len = len(text)
        
        # 遍历语义池（由于是内存遍历，控制在几千条内很快）
        for cached_text, result in self._text_pool.items():
            # 长度相差太大直接跳过
            if abs(len(cached_text) - t_len) > 2: continue
            
            c_set = set(cached_text)
            intersection = len(t_set.intersection(c_set))
            union = len(t_set.union(c_set))
            similarity = intersection / union if union > 0 else 0
            
            if similarity > 0.9: # 高度相似 (如: "这个好漂亮" vs "这个好漂亮呀")
                res = result.copy()
                res["reasoning"] = f"[相似度命中: {cached_text}] {res.get('reasoning', '')}"
                return res
        return None

    def _get_file_md5(self, file_path: str) -> str:
        """计算文件的 MD5 哈希值。"""
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except:
            return ""

    def _get_content_signature(self, text: str, images: List[str]) -> str:
        """生成内容的唯一指纹（文本归一化 + 图像 MD5）。"""
        # 1. 文本归一化 (去除多余空格、统一表情符号占位符等)
        normalized_text = re.sub(r'\s+', ' ', text).strip()
        
        # 2. 图像哈希列表 (排序以保证顺序无关性)
        img_hashes = []
        for img in images:
            h = self._get_file_md5(img)
            if h: img_hashes.append(h)
        img_hashes.sort()
        
        # 3. 组合签名
        sig_base = f"T:{normalized_text}|I:{','.join(img_hashes)}"
        return hashlib.md5(sig_base.encode('utf-8')).hexdigest()

    def _get_cache_key(self, text: str, images: List[str]) -> Optional[str]:
        """已弃用，使用 _get_content_signature。"""
        return self._get_content_signature(text, images)

    def _input_with_timeout(self, prompt: str, timeout: int = 20) -> Optional[str]:
        """带有超时机制的输入函数。"""
        result = [None]
        def get_input():
            try:
                result[0] = input(prompt).strip()
            except EOFError:
                pass

        thread = threading.Thread(target=get_input)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            utils.logger.warning(f"\n[MultimodalAnalyzer._input_with_timeout] [超时] 超过 {timeout}s 未输入，将由系统自动标注。")
            return None
        return result[0]

    def process_batch(self, data: List[Dict[str, Any]], exporter=None, batch_size: int = 8, use_lock: bool = True) -> List[Dict[str, Any]]:
        """
        处理数据批次，实现 CPU 与 GPU 的流水线并行：
        - 方案 A: 纯文本数据分流，使用大批次并行
        - 方案 B: 使用预取队列实现 CPU 预处理与 GPU 推理的并行
        """
        if self.adaptive_batch_size is None:
            self.adaptive_batch_size = batch_size

        # --- 逻辑去重 (作为二次验证) ---
        if exporter:
            existing_ids = exporter.get_existing_ids()
            if existing_ids:
                data_len_before = len(data)
                data = [item for item in data if f"{item.get('note_id')}_{item.get('comment_id')}" not in existing_ids]
                filtered_count = data_len_before - len(data)
                if filtered_count > 0:
                    utils.logger.info(f"[MultimodalAnalyzer.process_batch] [断点续传] 已过滤掉 {filtered_count} 条已处理的数据，剩余 {len(data)} 条。")

        if not data:
            utils.logger.info("[MultimodalAnalyzer.process_batch] [完成] 没有新数据需要处理。")
            return []

        # --- 数据分流 (核心优化 2) ---
        text_only_data = []
        multimodal_data = []
        for item in data:
            if not item.get("images"):
                text_only_data.append(item)
            else:
                multimodal_data.append(item)

        utils.logger.info(f"[MultimodalAnalyzer.process_batch] 📊 数据分流报告")
        utils.logger.info(f"[MultimodalAnalyzer.process_batch] • 纯文本流: {len(text_only_data)} 条 -> [策略: 跳过视觉编码, 稳定 Batch=32]")
        utils.logger.info(f"[MultimodalAnalyzer.process_batch] • 多模态流: {len(multimodal_data)} 条 -> [策略: 开启视觉编码, 标准 Batch={self.adaptive_batch_size}]")
        utils.logger.info("-" * 60)
        
        analyzed_data = []
        overall_start_time = time.time()
        
        def _preprocess_text(text: str) -> str:
            """针对超长文本进行关键信息提取，减少 pre-fill 压力。"""
            if not text: return ""
            # 去除超长重复字符，防止干扰 LLM
            text = re.sub(r'(.)\1{20,}', r'\1\1\1...', text)
            # 去除换行符和多余空格
            text = " ".join(text.split())
            if len(text) > 800:
                # 保留头部 400 字和尾部 400 字，中间用省略号代替
                return f"{text[:400]}\n...[中间内容已略过]...\n{text[-400:]}"
            return text

        # 定义内部处理逻辑
        def run_pipeline(target_data, current_bs, mode_name):
            if not target_data: return

            # 针对纯文本流优化：按长度排序，形成“长度桶”，减少推理时的 Padding 开销
            if mode_name == "纯文本":
                target_data.sort(key=lambda x: len(x.get("content", "")))
                utils.logger.info(f"[MultimodalAnalyzer.run_pipeline] [优化] 纯文本流已按长度排序，减少 GPU Padding 开销")

            total_target = len(target_data)
            processed_target = 0
            start_global_time = time.time() # 记录程序启动总时间
            
            # 预取线程
            def prefetch_worker():
                idx = 0
                while idx < total_target:
                    # --- 动态 Batch Size 逻辑 ---
                    # 基础策略：如果是多模态模式，且单条数据图片较多，则缩小 Batch
                    # 避免在 6GB 显存上出现 OOM
                    actual_bs = current_bs
                    if mode_name == "多模态":
                        # 预看一眼接下来的数据
                        lookahead = target_data[idx : idx + current_bs]
                        total_imgs = sum(len(item.get("images", [])) for item in lookahead)
                        if total_imgs > 8: # 平均每条数据超过 1 张图，且总数较多
                            actual_bs = max(4, current_bs // 2)
                        elif total_imgs > 16:
                            actual_bs = 2
                    
                    batch_items = target_data[idx : idx + actual_bs]
                    
                    vlm_batch_data = []
                    batch_results = [None] * len(batch_items)
                    cached_indices = []
                    
                    if actual_bs != current_bs:
                        utils.logger.info(f"[MultimodalAnalyzer.prefetch_worker] 策略: 视觉压力较大，动态调整 Batch Size: {current_bs} -> {actual_bs}")
                    
                    utils.logger.info(f"[MultimodalAnalyzer.prefetch_worker] CPU: 正在预处理第 {idx//current_bs + 1} 批数据 ({mode_name})")
                    
                    # 使用线程池并行计算 MD5 和签名
                    def prepare_item(item_data):
                        text = item_data.get("content", "") or "[无文本内容]"
                        my_images = item_data.get("images", [])
                        sig = self._get_content_signature(text, my_images)
                        return item_data, sig, text, my_images

                    prepared_items = list(self.cpu_executor.map(prepare_item, batch_items))

                    for b_idx, (item, sig, text, my_images) in enumerate(prepared_items):
                        # --- 核心优化 1: 全量内容哈希命中 ---
                        if sig in self._analysis_cache:
                            analysis = self._analysis_cache[sig].copy()
                            item["analysis"] = analysis
                            batch_results[b_idx] = analysis
                            cached_indices.append(b_idx)
                            continue

                        # --- 核心优化 2: 纯文本快速路径 (Fast Path) ---
                        # 仅针对无图片的情况
                        if not my_images:
                            fast_res = self._check_fast_path(text)
                            if fast_res:
                                item["analysis"] = fast_res
                                batch_results[b_idx] = fast_res
                                cached_indices.append(b_idx)
                                # 存入全量缓存以便下次直接命中
                                self._analysis_cache[sig] = fast_res
                                continue
                            
                            # --- 核心优化 3: 语义相似度匹配 ---
                            sim_res = self._check_semantic_similarity(text)
                            if sim_res:
                                item["analysis"] = sim_res
                                batch_results[b_idx] = sim_res
                                cached_indices.append(b_idx)
                                self._analysis_cache[sig] = sim_res
                                continue

                        # --- 核心优化 4: 视觉特征迁移 (Vision Knowledge Transfer) ---
                        known_visual_info = []
                        for img in my_images:
                            h = self._get_file_md5(img)
                            if h in self._vision_cache:
                                v_info = self._vision_cache[h]
                                info_str = f"[已知图片特征: OCR={v_info.get('ocr_text','')}, 对象={v_info.get('objects',[])}]"
                                known_visual_info.append(info_str)
                        
                        can_downgrade_to_text = len(known_visual_info) == len(my_images) and len(my_images) > 0

                        # --- 核心优化 5: 上下文智能精简 (Prompt Compression) ---
                        # 为了准确判断情感极性（尤其是讽刺/反转），子评论必须结合对话链上下文
                        item_type = item.get('type', 'item')
                        parent_content = item.get("parent_content", "")  # 文章内容
                        reply_to_content = item.get("reply_to_content", "") # 父评论内容
                        
                        context_parts = []
                        if parent_content:
                            # 尝试获取文章的分析结果（情感、视觉信息）
                            note_id = item.get("note_id")
                            post_analysis = None
                            
                            # 1. 查内存缓存
                            if note_id in self._post_context_cache:
                                post_analysis = self._post_context_cache[note_id]
                            # 2. 查 Exporter 数据库 (如果提供了 exporter)
                            elif exporter:
                                post_analysis = exporter.get_post_analysis(note_id)
                                if post_analysis:
                                    self._post_context_cache[note_id] = post_analysis
                            
                            # 构建增强的背景信息
                            p_text = _preprocess_text(parent_content)
                            
                            if post_analysis:
                                # 如果有分析结果，注入情感和视觉信息
                                p_sentiment = post_analysis.get("sentiment", "未知")
                                p_objects = post_analysis.get("visual_objects", [])
                                p_ocr = post_analysis.get("ocr_text", "")
                                
                                # 如果原 parent_content 只是占位符，尝试用分析结果中的 content 替换
                                if (p_text == "[图片内容]" or not p_text) and post_analysis.get("content"):
                                    p_text = _preprocess_text(post_analysis.get("content"))

                                extra_info = []
                                if p_sentiment: extra_info.append(f"情感:{p_sentiment}")
                                if p_objects: extra_info.append(f"视觉:{','.join(p_objects[:5])}")
                                if p_ocr: extra_info.append(f"OCR:{p_ocr[:50]}...")
                                
                                context_parts.append(f"[文章背景 ({' '.join(extra_info)})]: {p_text[:200]}")
                            else:
                                # 降级：仅使用文本
                                truncated_p = p_text[:150] + "..." if len(p_text) > 150 else p_text
                                context_parts.append(f"[文章背景]: {truncated_p}")
                        
                        if reply_to_content:
                            # 对话链上下文：子评论回复的对象内容，保留前 100 字
                            r_text = _preprocess_text(reply_to_content)
                            truncated_r = r_text[:100] + "..." if len(r_text) > 100 else r_text
                            context_parts.append(f"[上级评论]: {truncated_r}")
                        
                        if context_parts:
                            context_str = "\n".join(context_parts)
                            full_prompt_text = f"{context_str}\n\n[待分析目标 - {item_type}内容]:\n{text}"
                        else:
                            full_prompt_text = f"[待分析目标 - {item_type}内容]:\n{text}"
                        
                        # 优化 3：针对纯图片数据的特殊 Prompt 引导
                        if text in ["[图片内容]", "[图片评论]"] and my_images:
                            full_prompt_text = f"{full_prompt_text}\n\n(系统提示: 该内容为纯图片/表情包，请重点通过视觉信息分析其表达的情感极性、意图及是否包含讽刺。)"
                        
                        if known_visual_info:
                            full_prompt_text = f"{full_prompt_text}\n\n(系统提示: 检测到已知图片，参考视觉信息: {' | '.join(known_visual_info)})"
                        
                        # 如果可以降级，我们依然标记为纯文本处理，但不传 images 给 VLM
                        current_images = [] if can_downgrade_to_text else my_images[:4]

                        vlm_batch_data.append({
                            "prompt_text": full_prompt_text, 
                            "images": current_images, 
                            "item_idx": b_idx,
                            "sig": sig,
                            "is_downgraded": can_downgrade_to_text
                        })
                    
                    preprocessed_inputs = None
                    if vlm_batch_data:
                        try:
                            from ..config import ANALYSIS_PROMPT
                            utils.logger.info(f"[MultimodalAnalyzer.prefetch_worker] CPU: 执行 Token 编码与张量化...")
                            preprocessed_inputs = self.vlm.preprocess_batch(vlm_batch_data, ANALYSIS_PROMPT)
                        except Exception as e:
                            utils.logger.error(f"[MultimodalAnalyzer.prefetch_worker] CPU 错误: 预处理失败: {e}")

                    self.prefetch_queue.put({
                        "batch_items": batch_items,
                        "vlm_batch_data": vlm_batch_data,
                        "preprocessed_inputs": preprocessed_inputs,
                        "batch_results": batch_results,
                        "cached_indices": cached_indices
                    })
                    idx += len(batch_items)
                self.prefetch_queue.put(None)

            p_thread = threading.Thread(target=prefetch_worker, daemon=True)
            p_thread.start()

            # 主循环
            while True:
                batch_package = self.prefetch_queue.get()
                if batch_package is None: break
                
                batch_items = batch_package["batch_items"]
                vlm_batch_data = batch_package["vlm_batch_data"]
                preprocessed_inputs = batch_package.get("preprocessed_inputs")
                batch_results = batch_package["batch_results"]
                cached_indices = batch_package["cached_indices"]
                
                if vlm_batch_data:
                    try:
                        vlm_start = time.time()
                        from ..config import ANALYSIS_PROMPT
                        
                        utils.logger.info(f"[MultimodalAnalyzer.run_pipeline] [GPU] 正在推理批次 (Batch: {len(vlm_batch_data)} | 模式: {mode_name})")
                        # 仅执行 GPU 推理，不执行解码和后处理
                        raw_outputs = self.vlm.analyze_batch(vlm_batch_data, ANALYSIS_PROMPT, preprocessed_inputs=preprocessed_inputs)
                        vlm_duration = time.time() - vlm_start
                        
                        # --- 核心优化：异步后处理 (CPU) ---
                        # 将解码、解析、缓存更新、导出全部交给 CPU 线程池，主线程立即进入下一轮推理
                        def async_post_process(items, v_data_list, outputs, start_time, duration):
                            try:
                                # 内部引用 batch_results，因为它是在 run_pipeline 作用域内分配的
                                # 且长度固定为 len(items)
                                post_start = time.time()
                                valid_items = []
                                for v_data, raw_output in zip(v_data_list, outputs):
                                    b_idx = v_data["item_idx"]
                                    if b_idx >= len(items):
                                        utils.logger.warning(f"  [MultimodalAnalyzer.async_post_process] 后处理警告: 索引越界: b_idx={b_idx}, items_len={len(items)}")
                                        continue
                                        
                                    item = items[b_idx]
                                    sig = v_data.get("sig")
                                    
                                    analysis = self._parse_vlm_output(raw_output, has_images=bool(item.get("images")))
                                    
                                    if sig:
                                        self._analysis_cache[sig] = analysis.copy()
                                    
                                    item_text = item.get("content", "")
                                    if not item.get("images") and len(item_text) > 5:
                                        self._text_pool[item_text] = analysis.copy()
                                    
                                    if item.get("images") and not v_data.get("is_downgraded"):
                                        for img in item["images"]:
                                            h = self._get_file_md5(img)
                                            if h and h not in self._vision_cache:
                                                self._vision_cache[h] = {
                                                    "objects": analysis.get("visual_objects", []),
                                                    "ocr_text": analysis.get("ocr_text", "")
                                                }

                                    item["analysis"] = analysis
                                    # 注意：这里直接修改 item 字典，外层 analyzed_data 也会同步更新
                                    valid_items.append(item)
                                    
                                    # [NEW] 如果是文章，缓存分析结果供后续评论使用
                                    note_id = item.get("note_id")
                                    comment_id = str(item.get("comment_id", "0"))
                                    if note_id and (comment_id == "0" or not comment_id):
                                        self._post_context_cache[note_id] = analysis.copy()
                                
                                if exporter and valid_items:
                                    exporter.export(valid_items, append=True, use_lock=use_lock)
                                
                                nonlocal processed_target
                                processed_target += len(items)
                                from datetime import datetime
                                timestamp = datetime.now().strftime("%H:%M:%S")
                                
                                # 计算总运行时间
                                elapsed_total = time.time() - start_global_time
                                hours, rem = divmod(elapsed_total, 3600)
                                minutes, seconds = divmod(rem, 60)
                                time_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
                                
                                # 根据数据类型选择 ID：文章输出 note_id，评论输出 comment_id
                                batch_ids = []
                                for it in items:
                                    cid = str(it.get('comment_id', '0'))
                                    if cid == '0':
                                        # 文章数据
                                        batch_ids.append(str(it.get('note_id', 'Unknown')))
                                    else:
                                        # 评论数据
                                        batch_ids.append(cid)
                                        
                                # 如果 ID 列表太长，只显示前两个和最后一个
                                if len(batch_ids) > 5:
                                    ids_summary = f"{batch_ids[0]}, {batch_ids[1]} ... {batch_ids[-1]}"
                                else:
                                    ids_summary = "，".join(batch_ids)
                                    
                                post_duration = time.time() - post_start
                                # 统一日志输出格式，增加运行时间统计
                                utils.logger.info(f"[MultimodalAnalyzer.async_post_process] [{timestamp}] [总计 {time_str}] [进度 {processed_target}/{total_target}] ID: [{ids_summary}]")
                                utils.logger.info(f"[MultimodalAnalyzer.async_post_process] 性能: 推理 {duration:.2f}s | 后处理 {post_duration:.2f}s")
                                
                                # 定期存盘
                                if len(self._analysis_cache) % 100 == 0:
                                    self._save_persistent_cache()
                            except Exception as ex:
                                utils.logger.error(f"  [MultimodalAnalyzer.async_post_process] 后处理错误: {ex}")

                        # 提交到线程池执行
                        self.cpu_executor.submit(async_post_process, batch_items, vlm_batch_data, raw_outputs, vlm_start, vlm_duration)

                    except Exception as e:
                        utils.logger.error(f"  [MultimodalAnalyzer.run_pipeline] [GPU 错误] 批次推理失败: {e}")
                        for b_idx, item in enumerate(batch_items):
                            if batch_results[b_idx] is None:
                                item["analysis"] = {"sentiment": "Unknown", "error": str(e)}
                                batch_results[b_idx] = item["analysis"]
                
                # 处理已经命中的缓存
                if cached_indices:
                    cached_items = [batch_items[idx] for idx in cached_indices]
                    
                    # [NEW] 缓存命中的文章也需要更新到 context cache
                    for item in cached_items:
                        note_id = item.get("note_id")
                        comment_id = str(item.get("comment_id", "0"))
                        if note_id and (comment_id == "0" or not comment_id):
                            analysis = item.get("analysis")
                            if analysis:
                                self._post_context_cache[note_id] = analysis.copy()

                    if exporter:
                        # 再次确保缓存命中的项不会导致重复写入（防止同一批次内多次命中相同 sig）
                        exporter.export(cached_items, append=True, use_lock=use_lock)
                
                for b_idx, item in enumerate(batch_items):
                    item["analysis"] = batch_results[b_idx]
                    analyzed_data.append(item)

        # 1. 先处理纯文本数据 (使用稳定批次: 32)
        if text_only_data:
            utils.logger.info(f"[MultimodalAnalyzer.process_batch] 🚀 启动阶段 1: 纯文本并行推理流 (稳定模式)")
            run_pipeline(text_only_data, current_bs=32, mode_name="纯文本")

        # 2. 再处理多模态数据 (使用原批次)
        if multimodal_data:
            utils.logger.info(f"[MultimodalAnalyzer.process_batch] 🚀 启动阶段 2: 多模态图文推理流 (精准模式)")
            run_pipeline(multimodal_data, current_bs=self.adaptive_batch_size, mode_name="多模态")

        utils.logger.info(f"[MultimodalAnalyzer.process_batch] 完成: 总耗时: {(time.time() - overall_start_time)/60:.1f}min")
        return analyzed_data

    def analyze_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single post or comment with context injection."""
        item_type = item.get('type', 'item')
        text = item.get("content", "") or "[无文本内容]"
        
        full_prompt_text = text
        if item.get("parent_content"):
            # 明确标注上下文与目标，引导模型正确分配权重
            full_prompt_text = f"上下文 (Context - 原贴内容):\n{item['parent_content']}\n\n目标 (Target - {item_type}内容):\n{text}"
        else:
            full_prompt_text = f"目标 (Target - {item_type}内容):\n{text}"
        
        # 仅使用自己的图片
        my_images = item.get("images", [])
        all_relevant_images = my_images[:4]
        
        image_description = ""
        if all_relevant_images:
            image_description = f"目标 (Target) 附带了 {len(all_relevant_images)} 张图片。\n"
        else:
            image_description = "目标 (Target) 没有附带图片。\n"
        
        full_prompt_text = f"{image_description}\n{full_prompt_text}"
        
        # GPU 推理
        raw_output = self.vlm.analyze(full_prompt_text, all_relevant_images, ANALYSIS_PROMPT)
        analysis = self._parse_vlm_output(raw_output, has_images=bool(all_relevant_images))
        
        if not all_relevant_images:
            analysis["objects"] = []
            analysis["ocr_text"] = ""
            
        # 再次确保 JSON 格式化输出不包含模型可能生成的虚假图片 URL 或幻觉
        if "objects" in analysis and isinstance(analysis["objects"], list):
            analysis["objects"] = [o for o in analysis["objects"] if isinstance(o, str) and not o.startswith("http")]
            
        item["analysis"] = analysis
        return item

    def _manual_annotate(self, item: Dict[str, Any], images: List[str], force: bool = False) -> Dict[str, Any]:
        """Prompt user for manual annotation in the console."""
        text = item.get("content", "")
        item_type = item.get("type", "item")
        
        utils.logger.warning("="*50)
        utils.logger.warning("[MultimodalAnalyzer._manual_annotate] ⚠️  触发手动标注模式")
        utils.logger.info(f"[MultimodalAnalyzer._manual_annotate] 类型: {item_type}")
        utils.logger.info(f"[MultimodalAnalyzer._manual_annotate] 内容文本: {text}")
        if item.get("parent_content"):
             utils.logger.info(f"[MultimodalAnalyzer._manual_annotate] 原帖内容: {item['parent_content']}")
        utils.logger.info("-" * 50)
        utils.logger.info("[MultimodalAnalyzer._manual_annotate] 图片列表 (点击可打开):")
        for img_rel in images:
            abs_path = Path(img_rel).absolute()
            clickable_path = abs_path.as_uri()
            utils.logger.info(f"  - {clickable_path}")
        utils.logger.info("-" * 50)
        
        if not force:
            choice = self._input_with_timeout("是否需要手动标注此项? (y/n, 默认n, 20s后跳过): ", 20)
            if choice is None or choice.lower() != 'y':
                utils.logger.info("[MultimodalAnalyzer._manual_annotate] >>> 跳过手动标注，交由系统分析...")
                return None
        else:
            utils.logger.warning("[MultimodalAnalyzer._manual_annotate] >>> VLM 发生错误，必须手动标注。")
        
        utils.logger.info(f"[MultimodalAnalyzer._manual_annotate] 可用主情感: {' / '.join(SENTIMENT_CATEGORIES)}")
        sentiment = self._input_with_timeout("请输入主情感标签: ", 20)
        if sentiment is None: return None

        utils.logger.info(f"[MultimodalAnalyzer._manual_annotate] 可用细粒度情感: {' / '.join(FINE_GRAINED_SENTIMENT_CATEGORIES)}")
        fine_grained = self._input_with_timeout("请输入细粒度情感标签: ", 20)
        if fine_grained is None: return None

        utils.logger.info(f"[MultimodalAnalyzer._manual_annotate] 可用意图: {' / '.join(INTENT_CATEGORIES)}")
        intent = self._input_with_timeout("请输入意图标签: ", 20)
        if intent is None: return None
            
        irony_input = self._input_with_timeout("是否包含反讽? (y/n, 默认n): ", 20)
        if irony_input is None: return None
        irony = irony_input.lower() == 'y'
        
        reasoning = self._input_with_timeout("请输入标注理由 (直接回车跳过): ", 20)
        if reasoning is None: reasoning = "人工手动标注"
        
        keywords = self._input_with_timeout("请输入关键词 (空格分隔): ", 20)
        keywords_list = keywords.split() if keywords else []

        return {
            "sentiment": sentiment,
            "fine_grained_sentiment": fine_grained,
            "intent": intent,
            "irony_detected": irony,
            "reasoning": reasoning or "人工手动标注",
            "keywords": keywords_list,
            "objects": ["Manual Label"],
            "ocr_text": "Manual Label",
            "is_manual": True
        }

    def _normalize_categories(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """对 AI 输出的意图和情感进行翻译和基础清洗，不再强制归一化到固定类别。"""
        # 1. 建立更全面的中英映射表
        translation_map = {
            # 意图类 (Intent)
            "recommendation": "推荐/安利",
            "seeking_advice": "求助/咨询",
            "seeking advice": "求助/咨询",
            "sharing": "分享/展示",
            "opinion_expression": "表达观点",
            "opinion expression": "表达观点",
            "emotional_venting": "情绪宣泄",
            "emotional venting": "情绪宣泄",
            "complaint": "吐槽/投诉",
            "praise": "赞赏",
            "questioning": "质疑/反驳",
            "humor": "幽默/讽刺",
            "irony": "幽默/讽刺",
            "news_report": "资讯发布",
            "news report": "资讯发布",
            "advertisement": "广告/营销",
            "marketing": "广告/营销",
            "gratitude": "祈祷/感谢",
            "thanks": "祈祷/感谢",
            "expectation": "期待/愿望",
            "wish": "期待/愿望",
            "daily_life": "日常碎碎念",
            "daily life": "日常碎碎念",
            "others": "其他",
            "other": "其他",
            
            # 情感类 (Sentiment)
            "positive": "正面",
            "negative": "负面",
            "neutral": "中立",
            "joy": "愉快",
            "happy": "愉快",
            "anger": "愤怒",
            "angry": "愤怒",
            "sadness": "悲伤",
            "sad": "悲伤",
            "fear": "恐惧",
            "disgust": "厌恶",
            "surprise": "惊喜",
            "anxiety": "焦虑",
            "anxious": "焦虑",
            "moved": "感动",
            "hope": "期待",
        }

        # 2. 获取原始值
        sentiment = result.get("sentiment", "Unknown")
        fine_grained = result.get("fine_grained_sentiment", "Unknown")
        intent = result.get("intent", "Unknown")

        # 3. 翻译与清洗逻辑
        def translate_val(val):
            if not isinstance(val, str):
                return "Unknown"
            
            # 清理：去除 "type:", "category:" 等前缀
            val = re.sub(r'^(type|category|intent|sentiment)\s*:\s*', '', val, flags=re.IGNORECASE)
            val = val.strip().lower()
            
            # 针对 "type" 这个词本身进行拦截，如果 AI 只输出了 "type"
            if val == "type" or not val:
                return "Unknown"
            
            # 尝试在映射表中寻找
            if val in translation_map:
                return translation_map[val]
            
            # 如果包含英文但不在表中，且长度较短（可能是漏掉的类别词），设为 Unknown 或尝试清洗
            if re.search(r'[a-zA-Z]', val):
                # 再次尝试模糊匹配（如 "sharing content" -> "sharing"）
                for eng, chn in translation_map.items():
                    if eng in val:
                        return chn
                return "Unknown" # 实在无法识别的英文回退到 Unknown
            
            return result.get(val, val) # 返回原始值（如果是中文则保留）

        result["sentiment"] = translate_val(sentiment)
        result["fine_grained_sentiment"] = translate_val(fine_grained)
        result["intent"] = translate_val(intent)
            
        return result

    def _parse_vlm_output(self, output: str, has_images: bool = True) -> Dict[str, Any]:
        """Extract JSON from VLM string output and normalize fields with high fault tolerance."""
        result = {}
        try:
            # 1. 预处理：去除可能的模型思考过程 (如 <thought> 标签)
            output = re.sub(r'<thought>.*?</thought>', '', output, flags=re.DOTALL)
            
            # 2. 尝试寻找 JSON 块
            json_str = None
            # 优先匹配 ```json ... ```
            json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 其次匹配 ``` ... ``` (如果不带 json 标识)
                json_match = re.search(r'```\s*(.*?)\s*```', output, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # 最后匹配第一个 { 和最后一个 } 之间的内容
                    json_match = re.search(r'(\{.*\})', output, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
            
            if json_str:
                # 尝试修复常见的 JSON 错误
                json_str = re.sub(r',\s*\}', '}', json_str)
                json_str = re.sub(r',\s*\]', ']', json_str)
                try:
                    parsed = json.loads(json_str)
                    # 确保解析出来的是字典
                    if isinstance(parsed, dict):
                        result = parsed
                    elif isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
                        result = parsed[0]
                except json.JSONDecodeError:
                    # 如果仍然失败，尝试更激进的修复：查找缺失的闭合括号
                    if json_str.count('{') > json_str.count('}'):
                        json_str += '}' * (json_str.count('{') - json_str.count('}'))
                    try:
                        result = json.loads(json_str)
                    except:
                        pass # 依然失败则进入手动提取逻辑

            # 3. 如果 JSON 解析完全失败，使用正则手动提取关键字段
            if not result:
                result = {
                    "sentiment": self._regex_extract(output, r'sentiment["\s:]+([^"\s,}\]]+)'),
                    "fine_grained_sentiment": self._regex_extract(output, r'fine_grained_sentiment["\s:]+([^"\s,}\]]+)'),
                    "intent": self._regex_extract(output, r'intent["\s:]+([^"\s,}\]]+)'),
                    "reasoning": self._regex_extract(output, r'reasoning["\s:]+["\']([^"\']+)["\']'),
                }
                # 如果还是空的，说明真的没输出
                if not any(result.values()):
                    raise ValueError("No JSON or valid fields found in output")

            # 4. 填充默认值，防止字段缺失
            defaults = {
                "sentiment": "Unknown",
                "fine_grained_sentiment": "Unknown",
                "intent": "Unknown",
                "irony_detected": False,
                "reasoning": "No reasoning provided",
                "keywords": [],
                "objects": [],
                "ocr_text": ""
            }
            for key, val in defaults.items():
                if key not in result or result[key] is None or result[key] == "":
                    result[key] = val

            # --- 核心修复：强制字段类型，解决 unhashable type: 'dict' 错误 ---
            for field in ["sentiment", "fine_grained_sentiment", "intent"]:
                # 如果是字典，尝试提取 True 的键或第一个键
                if isinstance(result[field], dict):
                    true_keys = [str(k) for k, v in result[field].items() if v is True]
                    result[field] = true_keys[0] if true_keys else next(iter(result[field].keys()), "Unknown")
                # 如果是列表，取第一个
                elif isinstance(result[field], list):
                    result[field] = str(result[field][0]) if result[field] else "Unknown"
                
                # 确保最终是清理过的字符串
                if not isinstance(result[field], str):
                    result[field] = str(result[field])
                
                result[field] = re.sub(r'[^\w\u4e00-\u9fa5/]', '', result[field]).strip()

            # 5. 归一化处理
            # 列表类字段归一化
            for field in ["objects", "keywords"]:
                if field in result and isinstance(result[field], list):
                    normalized = []
                    for val in result[field]:
                        if isinstance(val, str):
                            if not val.startswith("http") and not val.startswith("https"):
                                normalized.append(val)
                    result[field] = list(set(normalized))

            # 6. 分类一致性自动修正
            result = self._normalize_categories(result)

            # 7. 无图片时的幻觉清理 (New!)
            if not has_images:
                result["objects"] = []
                result["ocr_text"] = ""
                if "reasoning" in result and isinstance(result["reasoning"], str):
                    # 强力移除“图片、图中、视觉”等相关幻觉描述
                    reasoning = result["reasoning"]
                    # 匹配常见的图片描述句式并移除
                    reasoning = re.sub(r'[^，。？！]*?(图片|图中|视觉|图像|视觉对象)[^，。？！]*?(显示|表达|看出|分析|说明|呈现|内容是)[^，。？！]*?[，。？！]', '', reasoning)
                    reasoning = re.sub(r'(根据|结合|通过)(图片|视觉|图像|视觉对象)[^，。？！]*', '', reasoning)
                    # 替换剩余的关键词
                    reasoning = re.sub(r'(图片|图中|视觉|图像)', '内容', reasoning)
                    result["reasoning"] = reasoning.strip(" ，。？！")
                    if not result["reasoning"]:
                        result["reasoning"] = "基于文本内容分析"

            return result

        except Exception as e:
            return {
                "error": str(e),
                "raw_output": output,
                "sentiment": "Unknown",
                "intent": "Unknown",
                "irony_detected": False,
                "reasoning": f"Failed to parse model output: {e}"
            }

    def _regex_extract(self, text: str, pattern: str) -> Optional[str]:
        """使用正则表达式提取字段值的辅助函数。"""
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip('"\' ')
        return None
