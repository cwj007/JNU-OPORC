import json
from typing import List, Dict, Any
from pathlib import Path

from ..config import PLATFORM_MAP, HISTORICAL_LABELED_DIR

class Exporter:
    def __init__(self, output_file: str):
        self.output_file = Path(output_file)

    def export(self, analyzed_data: List[Dict[str, Any]], append: bool = False):
        """Export analyzed data to JSONL format with the requested schema."""
        formatted_results = []
        
        # 尝试从数据中提取日期，用于保存历史备份
        data_date = None
        if analyzed_data:
            data_date = analyzed_data[0].get("data_date")
            
        for item in analyzed_data:
            formatted_entry = self._format_entry(item)
            formatted_results.append(formatted_entry)
        
        # 1. 保存到主结果文件
        mode = 'a' if append else 'w'
        with open(self.output_file, mode, encoding='utf-8') as f:
            for entry in formatted_results:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        
        # 2. 如果有日期，同时备份到 history 目录
        if data_date:
            history_file = HISTORICAL_LABELED_DIR / f"labeled_results_{data_date}.jsonl"
            with open(history_file, mode, encoding='utf-8') as f:
                for entry in formatted_results:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            print(f"Historical backup saved to: {history_file}")
        
        if not append:
            print(f"Exported {len(formatted_results)} records to {self.output_file}")

    def _format_entry(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Format a single item (post or comment) according to the user's schema."""
        analysis = item.get("analysis", {})
        
        # Combine image paths into content description if requested
        content = item.get("content", "")
        images = item.get("images", [])
        
        # Translate platform name
        raw_source = item.get("source", "unknown")
        source_name = PLATFORM_MAP.get(raw_source, raw_source)

        # 只有在检测到反讽时才在推理中体现相关说明
        irony_detected = analysis.get("irony_detected", False)
        reasoning = analysis.get("reasoning", "")
        if not irony_detected:
            # 如果没有反讽，清理推理过程中的反讽相关词汇，或者保持简洁
            reasoning = reasoning.split("，没有")[0].split(", no")[0]
        
        return {
            "top_id": item.get("top_id"),
            "note_id": item.get("note_id"),
            "comment_id": item.get("comment_id"),
            "content": content,
            "image_paths": images, # 存储图片相对路径
            "source": source_name, # 微博 / 知乎 等中文名
            "author": item.get("author", ""),
            "created_at": item.get("created_at", ""),
            "url": item.get("url"),
            "sentiment_analysis": {
                "sentiment": analysis.get("sentiment"),
                "fine_grained_sentiment": analysis.get("fine_grained_sentiment"),
                "intent": analysis.get("intent"),
                "irony_detected": irony_detected,
                "reasoning": reasoning
            },
            "labels": analysis.get("sentiment_labels", [analysis.get("sentiment")]),
            "keywords": analysis.get("keywords", []),
            "visual_objects": analysis.get("objects", []),
            "ocr_text": analysis.get("ocr_text", "")
        }
