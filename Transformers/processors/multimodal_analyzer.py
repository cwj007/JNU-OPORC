import json
import re
from typing import List, Dict, Any
from ..models.vlm_handler import VLMHandler
from ..config import ANALYSIS_PROMPT, MAX_IMAGES_FOR_VLM, SENTIMENT_CATEGORIES, INTENT_CATEGORIES

class MultimodalAnalyzer:
    def __init__(self, vlm_handler: VLMHandler):
        self.vlm = vlm_handler

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

    def _manual_annotate(self, text: str, images: List[str]) -> Dict[str, Any]:
        """Prompt user for manual annotation in the console."""
        print("\n" + "="*50)
        print("⚠️  触发手动标注模式")
        print(f"原因: 图片数量 ({len(images)}) 超过阈值 ({MAX_IMAGES_FOR_VLM})")
        print(f"内容文本: {text[:200]}...")
        print(f"图片路径: {images}")
        print("-" * 50)
        
        # Display options for quick reference
        print(f"可用情感: {' / '.join(SENTIMENT_CATEGORIES)}")
        sentiment = ""
        while not sentiment:
            sentiment = input("请输入情感标签: ").strip()
            
        print(f"可用意图: {' / '.join(INTENT_CATEGORIES)}")
        intent = ""
        while not intent:
            intent = input("请输入用户意图: ").strip()
            
        irony_input = input("是否包含反讽? (y/n, 默认n): ").lower().strip()
        irony = irony_input == 'y'
        
        reasoning = input("请输入标注理由 (直接回车跳过): ").strip()
        keywords = input("请输入关键词 (空格分隔): ").strip().split()

        return {
            "sentiment": sentiment,
            "intent": intent,
            "irony_detected": irony,
            "reasoning": reasoning or "人工手动标注 (图片过多)",
            "keywords": keywords,
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
            print(f"[{idx+1}/{total}] Analyzing {item_type} {note_id}...")
            
            # Use parent context if available (for comments)
            text = item.get("content", "")
            if item.get("parent_content"):
                text = f"Context (Original Post): {item['parent_content']}\nTarget ({item_type}): {text}"
            
            images = item.get("images", [])
            
            # Check for manual fallback threshold
            if len(images) > MAX_IMAGES_FOR_VLM:
                item["analysis"] = self._manual_annotate(text, images)
            else:
                # Call VLM
                try:
                    raw_output = self.vlm.analyze(text, images, ANALYSIS_PROMPT)
                    item["analysis"] = self._parse_vlm_output(raw_output)
                except Exception as e:
                    print(f"  VLM Error, falling back to manual: {e}")
                    item["analysis"] = self._manual_annotate(text, images)
            
            analyzed_data.append(item)
            
            # Incremental export
            if exporter:
                exporter.export([item], append=True)
            
        return analyzed_data
