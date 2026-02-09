import json
import re
import threading
import sys
import time
import queue
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..models.vlm_handler import VLMHandler
from ..config import ANALYSIS_PROMPT, MAX_IMAGES_FOR_VLM, SENTIMENT_CATEGORIES, FINE_GRAINED_SENTIMENT_CATEGORIES, INTENT_CATEGORIES, MEDIA_CRAWLER_DATA_DIR

class MultimodalAnalyzer:
    def __init__(self, vlm_handler: VLMHandler):
        self.vlm = vlm_handler
        self._analysis_cache = {} # 文本缓存，减少重复分析
        self.adaptive_batch_size = None # 动态调整的批大小
        self.prefetch_queue = queue.Queue(maxsize=2) # 预取队列 (方案 B)

    def _get_cache_key(self, text: str, images: List[str]) -> Optional[str]:
        """仅对无图片的纯文本内容进行缓存。"""
        if not images and text:
            return text.strip()
        return None

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
            print(f"\n[超时] 超过 {timeout}s 未输入，将由系统自动标注。")
            return None
        return result[0]

    def process_batch(self, data: List[Dict[str, Any]], exporter=None, batch_size: int = 8, use_lock: bool = True) -> List[Dict[str, Any]]:
        """
        处理数据批次，实现 CPU 与 GPU 的流水线并行：
        - 方案 B: 使用预取队列实现 CPU 预处理与 GPU 推理的并行
        """
        if self.adaptive_batch_size is None:
            self.adaptive_batch_size = batch_size

        # --- 逻辑去重 (作为二次验证) ---
        if exporter:
            existing_ids = exporter.get_existing_ids()
            if existing_ids:
                data = [item for item in data if f"{item.get('note_id')}_{item.get('comment_id')}" not in existing_ids]
                if 0 < len(data) < batch_size * 10: # 只有数据量够多才显示跳过信息
                    print(f"\n[断点续传] 已过滤掉已处理的数据，剩余 {len(data)} 条。")

        total = len(data)
        if total == 0:
            print("\n[完成] 没有新数据需要处理。")
            return []

        print(f"\n[并行模式] 已开启方案 B (异步预取) 与方案 A (纯文本提速)")
        print(f"总数据量: {total}, 批大小: {self.adaptive_batch_size}")
        
        analyzed_data = []
        overall_start_time = time.time()
        
        # 方案 B: 预处理工作线程
        def prefetch_worker():
            idx = 0
            while idx < total:
                curr_bs = self.adaptive_batch_size # 动态 BS
                batch_items = data[idx : idx + curr_bs]
                
                vlm_batch_data = []
                batch_results = [None] * len(batch_items)
                cached_indices = []
                
                for b_idx, item in enumerate(batch_items):
                    text = item.get("content", "") or "[无文本内容]"
                    my_images = item.get("images", [])
                    
                    cache_key = self._get_cache_key(text, my_images)
                    if cache_key and cache_key in self._analysis_cache:
                        analysis = self._analysis_cache[cache_key].copy()
                        item["analysis"] = analysis # 附加缓存结果
                        batch_results[b_idx] = analysis
                        cached_indices.append(b_idx)
                        continue

                    # 构造 Prompt
                    full_prompt_text = text
                    if item.get("parent_content"):
                        full_prompt_text = f"上下文: {item['parent_content']}\n\n目标: {text}"
                    
                    # 限制图片数量
                    all_relevant_images = my_images[:4]
                    vlm_batch_data.append({
                        "prompt_text": full_prompt_text, 
                        "images": all_relevant_images, 
                        "item_idx": b_idx
                    })
                
                # 方案 B: 在后台线程进行图像预处理
                preprocessed_inputs = None
                if vlm_batch_data:
                    try:
                        # 在后台线程提前编码图像和文本
                        from ..config import ANALYSIS_PROMPT
                        preprocessed_inputs = self.vlm.preprocess_batch(vlm_batch_data, ANALYSIS_PROMPT)
                    except Exception as e:
                        print(f"  [后台预处理错误] {e}")

                # 将预处理好的批次放入队列
                self.prefetch_queue.put({
                    "batch_items": batch_items,
                    "vlm_batch_data": vlm_batch_data,
                    "preprocessed_inputs": preprocessed_inputs, # 传递预处理结果
                    "batch_results": batch_results,
                    "cached_indices": cached_indices,
                    "start_idx": idx
                })
                idx += len(batch_items)
            
            # 放入结束标志
            self.prefetch_queue.put(None)

        # 启动预取线程
        prefetch_thread = threading.Thread(target=prefetch_worker, daemon=True)
        prefetch_thread.start()

        # 主线程: GPU 推理与后处理
        processed_count = 0
        while True:
            batch_package = self.prefetch_queue.get()
            if batch_package is None:
                break
            
            batch_items = batch_package["batch_items"]
            vlm_batch_data = batch_package["vlm_batch_data"]
            preprocessed_inputs = batch_package.get("preprocessed_inputs")
            batch_results = batch_package["batch_results"]
            cached_indices = batch_package["cached_indices"]
            
            # --- GPU 阶段 ---
            if vlm_batch_data:
                try:
                    vlm_start = time.time()
                    # 使用预处理好的数据进行推理
                    from ..config import ANALYSIS_PROMPT
                    raw_outputs = self.vlm.analyze_batch(vlm_batch_data, ANALYSIS_PROMPT, preprocessed_inputs=preprocessed_inputs)
                    vlm_duration = time.time() - vlm_start
                    
                    # --- CPU 后处理 ---
                    valid_items = []
                    for v_data, raw_output in zip(vlm_batch_data, raw_outputs):
                        b_idx = v_data["item_idx"]
                        item = batch_items[b_idx]
                        analysis = self._parse_vlm_output(raw_output)
                        
                        # 存入缓存
                        cache_key = self._get_cache_key(item.get("content", ""), item.get("images", []))
                        if cache_key: self._analysis_cache[cache_key] = analysis.copy()
                            
                        # 重要：将分析结果附加到 item 对象上，以便后续导出
                        item["analysis"] = analysis
                        batch_results[b_idx] = analysis
                        valid_items.append(item)
                    
                    # 导出
                    if exporter and valid_items:
                        exporter.export(valid_items, append=True, use_lock=use_lock)
                    
                    processed_count += len(batch_items)
                    # 增强日志输出：显示时间戳和批次内所有数据的 ID 列表
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    # 提取批次内所有项的 ID (优先使用 comment_id，若为 0 或不存在则使用 note_id)
                    batch_ids = []
                    for item in batch_items:
                        c_id = str(item.get('comment_id', '0'))
                        if c_id != '0':
                            batch_ids.append(c_id)
                        else:
                            batch_ids.append(str(item.get('note_id', 'Unknown')))
                    
                    ids_str = "，".join(batch_ids)
                    print(f"\n[{timestamp}] [进度 {processed_count}/{total}] 批次 ID 列表: 【{ids_str}】")
                    print(f"  GPU 推理耗时: {vlm_duration:.2f}s ({vlm_duration/len(vlm_batch_data):.2f}s/条)")
                
                except Exception as e:
                    print(f"  [错误] 批次处理失败: {e}")
                    # 简单兜底
                    for b_idx, item in enumerate(batch_items):
                        if batch_results[b_idx] is None:
                            analysis = {"sentiment": "Unknown", "error": str(e)}
                            batch_results[b_idx] = analysis
                            item["analysis"] = analysis

            # 处理缓存命中的数据
            for idx in cached_indices:
                if exporter: exporter.export([batch_items[idx]], append=True, use_lock=use_lock)
            
            # 合并结果
            for b_idx, item in enumerate(batch_items):
                item["analysis"] = batch_results[b_idx]
                analyzed_data.append(item)

        print(f"\n[完成] 总耗时: {(time.time() - overall_start_time)/60:.1f}min")
        return analyzed_data
                    
        return analyzed_data

    def analyze_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single post or comment with context injection."""
        item_type = item.get('type', 'item')
        text = item.get("content", "") or "[无文本内容]"
        
        full_prompt_text = text
        if item.get("parent_content"):
            full_prompt_text = f"上下文 (Context - 原贴内容): {item['parent_content']}\n\n目标 (Target - {item_type}内容): {text}"
        
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
        analysis = self._parse_vlm_output(raw_output)
        
        if not my_images:
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
        
        print("\n" + "="*50)
        print("⚠️  触发手动标注模式")
        print(f"类型: {item_type}")
        print(f"内容文本: {text}")
        if item.get("parent_content"):
             print(f"原帖内容: {item['parent_content']}")
        
        # 处理图片路径为 Windows 可点击格式
        print("-" * 50)
        print("图片列表 (点击可打开):")
        for img_rel in images:
            abs_path = Path(img_rel)
            # 使用 pathlib 的 as_uri() 生成标准的 Windows 可点击路径
            clickable_path = abs_path.as_uri()
            print(f"  - {clickable_path}")
        print("-" * 50)

        # 1. 询问是否需要手动标注
        if not force:
            choice = self._input_with_timeout("是否需要手动标注此项? (y/n, 默认n, 20s后跳过): ", 20)
            if choice is None or choice.lower() != 'y':
                print(">>> 跳过手动标注，交由系统分析...")
                return None # 返回 None 触发 VLM 分析
        else:
            print(">>> VLM 发生错误，必须手动标注。")

        # 2. 进行标注
        print(f"可用主情感: {' / '.join(SENTIMENT_CATEGORIES)}")
        sentiment = self._input_with_timeout("请输入主情感标签: ", 20)
        if sentiment is None: return None

        print(f"可用细粒度情感: {' / '.join(FINE_GRAINED_SENTIMENT_CATEGORIES)}")
        fine_grained = self._input_with_timeout("请输入细粒度情感标签: ", 20)
        if fine_grained is None: return None
            
        print(f"可用意图: {' / '.join(INTENT_CATEGORIES)}")
        intent = self._input_with_timeout("请输入用户意图: ", 20)
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

    def _parse_vlm_output(self, output: str) -> Dict[str, Any]:
        """Extract JSON from VLM string output and normalize fields."""
        try:
            # Look for JSON block
            json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                # Try to find anything that looks like JSON
                json_match = re.search(r'\{.*\}', output, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    raise ValueError("No JSON found in output")

            # 1. 填充默认值，防止字段缺失导致输出 null
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
                if key not in result or result[key] is None:
                    result[key] = val

            # 2. 细粒度情感归一化 (防止模型输出 dict)
            fg = result.get("fine_grained_sentiment")
            if isinstance(fg, dict):
                true_keys = [str(k) for k, v in fg.items() if v is True]
                result["fine_grained_sentiment"] = true_keys[0] if true_keys else "中立"
            elif not isinstance(fg, str):
                result["fine_grained_sentiment"] = str(fg) if fg else "中立"

            # 3. 视觉对象和关键词归一化 (去重、过滤 URL、扁平化)
            for field in ["objects", "keywords"]:
                if field in result and isinstance(result[field], list):
                    normalized = []
                    for val in result[field]:
                        if isinstance(val, str):
                            if not val.startswith("http") and not val.startswith("https"):
                                normalized.append(val)
                        elif isinstance(val, dict):
                            normalized.extend([str(v) for v in val.values() if isinstance(v, str)])
                    result[field] = list(set(normalized))

            # 4. 反讽判定归一化
            irony = result.get("irony_detected")
            if isinstance(irony, str):
                result["irony_detected"] = irony.lower() == 'true'

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
