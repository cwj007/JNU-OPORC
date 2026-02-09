import json
import re
import threading
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..models.vlm_handler import VLMHandler
from ..config import ANALYSIS_PROMPT, MAX_IMAGES_FOR_VLM, SENTIMENT_CATEGORIES, FINE_GRAINED_SENTIMENT_CATEGORIES, INTENT_CATEGORIES, MEDIA_CRAWLER_DATA_DIR

class MultimodalAnalyzer:
    def __init__(self, vlm_handler: VLMHandler):
        self.vlm = vlm_handler

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

    def analyze_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single post or comment."""
        text = item.get("content", "")
        images = item.get("images", [])
        
        # Call VLM
        raw_output = self.vlm.analyze(text, images, ANALYSIS_PROMPT)
        
        # Parse JSON from VLM output
        analysis_result = self._parse_vlm_output(raw_output)
        
        # Merge with original item
        item["analysis"] = analysis_result
        return item

    def _parse_vlm_output(self, output: str) -> Dict[str, Any]:
        """Extract JSON from VLM string output."""
        try:
            # Look for JSON block
            json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            
            # Try to find anything that looks like JSON
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            
            # Fallback if parsing fails
            return {
                "error": "Could not parse VLM output as JSON",
                "raw_output": output,
                "sentiment": "Unknown",
                "intent": "Unknown",
                "irony_detected": False,
                "reasoning": "Failed to parse model output"
            }
        except Exception as e:
            return {"error": str(e), "raw_output": output}

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

    def process_batch(self, data: List[Dict[str, Any]], exporter=None) -> List[Dict[str, Any]]:
        """Process a flat list of items (posts and comments) and optionally export incrementally."""
        analyzed_data = []
        total = len(data)
        
        for idx, item in enumerate(data):
            note_id = item.get('note_id')
            item_type = item.get('type', 'item')
            print(f"\n[{idx+1}/{total}] Analyzing {item_type} {note_id}...")
            
            # Use parent context if available (for comments)
            text = item.get("content", "")
            full_prompt_text = text
            if item.get("parent_content"):
                full_prompt_text = f"Context (Original Post): {item['parent_content']}\nTarget ({item_type}): {text}"
            
            images = item.get("images", [])
            
            # 尝试手动标注或 VLM 分析
            analysis = None
            
            # 如果图片过多，优先触发手动标注询问
            if len(images) > MAX_IMAGES_FOR_VLM:
                print(f"提示：图片数量 ({len(images)}) 超过阈值 ({MAX_IMAGES_FOR_VLM})，准备触发手动标注询问。")
                analysis = self._manual_annotate(item, images)
            
            # 如果没有进行手动标注（用户拒绝或未触发），则调用 VLM
            if analysis is None:
                try:
                    # 只有在图片数量未超过阈值，或者用户拒绝了手动标注时，才调用 VLM
                    raw_output = self.vlm.analyze(full_prompt_text, images, ANALYSIS_PROMPT)
                    analysis = self._parse_vlm_output(raw_output)
                except Exception as e:
                    print(f"  VLM Error, falling back to manual: {e}")
                    # 出错时强制进入手动标注
                    analysis = self._manual_annotate(item, images, force=True)
                    # 如果第二次手动标注也超时/拒绝，则给一个空分析
                    if analysis is None:
                        analysis = {"error": str(e), "sentiment": "Unknown"}

            item["analysis"] = analysis
            analyzed_data.append(item)
            
            # Incremental export
            if exporter:
                exporter.export([item], append=True)
            
        return analyzed_data
