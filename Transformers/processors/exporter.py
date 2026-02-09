import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from filelock import FileLock

from ..config import PLATFORM_MAP, HISTORICAL_LABELED_DIR

class Exporter:
    def __init__(self, output_file: str):
        self.output_file = Path(output_file)
        self._existing_ids_cache = None # 内存缓存

    def get_existing_ids(self) -> set:
        """从主输出文件和历史目录中扫描所有已处理的 ID。"""
        if self._existing_ids_cache is not None:
            return self._existing_ids_cache
            
        existing_ids = set()
        
        # 1. 扫描历史目录中的所有 .jsonl 文件
        if HISTORICAL_LABELED_DIR.exists():
            for history_file in HISTORICAL_LABELED_DIR.glob("*.jsonl"):
                self._load_ids_from_file(history_file, existing_ids)
        
        # 2. 扫描当前主输出文件
        if self.output_file.exists():
            self._load_ids_from_file(self.output_file, existing_ids)
        
        self._existing_ids_cache = existing_ids
        return existing_ids

    def _load_ids_from_file(self, file_path: Path, id_set: set):
        """辅助函数：从单个文件读取 ID。"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        data = json.loads(line)
                        unique_id = f"{data.get('note_id')}_{data.get('comment_id')}"
                        id_set.add(unique_id)
                    except:
                        continue
        except Exception as e:
            print(f"Warning: Failed to read existing IDs from {file_path.name}: {e}")

    def export(self, analyzed_data: List[Dict[str, Any]], append: bool = False, use_lock: bool = True):
        """Export analyzed data to JSONL format and a structured JSON for frontend."""
        if not analyzed_data:
            return
            
        formatted_results = []
        data_date = analyzed_data[0].get("data_date")
            
        for item in analyzed_data:
            formatted_entry = self._format_entry(item)
            formatted_results.append(formatted_entry)
        
        # 1. 保存到原始结果文件 (JSONL)
        mode = 'a' if append else 'w'
        
        # 仅在需要时使用文件锁（多进程安全）
        if use_lock:
            lock_path = f"{self.output_file}.lock"
            with FileLock(lock_path):
                self._do_export(formatted_results, data_date, mode, append)
        else:
            self._do_export(formatted_results, data_date, mode, append)

    def _do_export(self, formatted_results, data_date, mode, append):
        """实际执行导出逻辑。"""
        existing_ids = self.get_existing_ids()

        valid_entries_to_write = []
        for entry in formatted_results:
            unique_id = f"{entry.get('note_id')}_{entry.get('comment_id')}"
            if unique_id not in existing_ids:
                valid_entries_to_write.append(entry)
                existing_ids.add(unique_id)

        if valid_entries_to_write:
            with open(self.output_file, mode, encoding='utf-8') as f:
                for entry in valid_entries_to_write:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            # 2. 生成聚合后的结构化数据
            self._export_aggregated_data(valid_entries_to_write, data_date, append)

            # 3. 如果有日期，同时备份到 history 目录
            if data_date:
                history_file = HISTORICAL_LABELED_DIR / f"labeled_results_{data_date}.jsonl"
                # 这里简单处理，历史备份也遵循锁逻辑
                with open(history_file, mode, encoding='utf-8') as f:
                    for entry in valid_entries_to_write:
                        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
                # 增强日志输出
                if len(valid_entries_to_write) <= 3:
                    ids_str = ", ".join([f"{e.get('note_id')}_{e.get('comment_id')}" for e in valid_entries_to_write])
                    print(f"  [存储] {len(valid_entries_to_write)} 条记录已同步 (ID: {ids_str})")
                else:
                    print(f"  [存储] {len(valid_entries_to_write)} 条新记录已同步至主文件及历史备份 (日期: {data_date})")
        
        if not append:
            print(f"Exported {len(formatted_results)} records to {self.output_file}")

    def _export_aggregated_data(self, results: List[Dict[str, Any]], data_date: str, append: bool):
        """将数据按文章聚合，并对标签/关键词进行去重，生成前端易用的 JSON。"""
        agg_file = self.output_file.parent / "aggregated_display_data.json"
        
        # 如果是追加模式，先读取现有数据
        aggregated = {}
        if append and agg_file.exists():
            try:
                with open(agg_file, 'r', encoding='utf-8') as f:
                    old_list = json.load(f)
                    for entry in old_list:
                        # 转换回 set 结构以便去重
                        if "summary" in entry:
                            s = entry["summary"]
                            s["all_keywords"] = set(s.get("all_keywords", []))
                            s["all_visual_objects"] = set(s.get("all_visual_objects", []))
                            s["all_labels"] = set(s.get("all_labels", []))
                        aggregated[entry['note_id']] = entry
            except Exception as e:
                print(f"Warning: Failed to load existing aggregated data: {e}")

        for item in results:
            note_id = item['note_id']
            comment_id = item['comment_id']
            is_comment = comment_id != "0"
            
            if note_id not in aggregated:
                aggregated[note_id] = {
                    "note_id": note_id,
                    "top_id": item.get("top_id"),
                    "url": item.get("url"),
                    "post_content": "",
                    "post_analysis": {},
                    "post_author": "",
                    "created_at": "",
                    "images": [],
                    "comments": [],
                    "summary": {
                        "all_keywords": set(),
                        "all_visual_objects": set(),
                        "all_labels": set(),
                        "sentiment_distribution": {"正面": 0, "中性": 0, "负面": 0}
                    }
                }
            
            target = aggregated[note_id]
            
            # 评论 ID 去重检查
            if is_comment:
                existing_comment_ids = [c["comment_id"] for c in target["comments"]]
                if comment_id in existing_comment_ids:
                    continue # 如果评论已存在，跳过该条数据的聚合
            
            analysis = item.get("sentiment_analysis", {})
            sentiment = analysis.get("sentiment")
            
            # 更新情感分布统计
            if sentiment in target["summary"]["sentiment_distribution"]:
                target["summary"]["sentiment_distribution"][sentiment] += 1
            
            # 聚合关键词、视觉对象和标签 (去重)
            if item.get("keywords"):
                target["summary"]["all_keywords"].update([str(k) for k in item["keywords"] if k])
            if item.get("visual_objects"):
                target["summary"]["all_visual_objects"].update([str(o) for o in item["visual_objects"] if o])
            if item.get("labels"):
                target["summary"]["all_labels"].update([str(l) for l in item["labels"] if l])
            
            fg_sentiment = analysis.get("fine_grained_sentiment")
            if fg_sentiment:
                if isinstance(fg_sentiment, str):
                    target["summary"]["all_labels"].add(fg_sentiment)
                elif isinstance(fg_sentiment, dict):
                    # 如果模型输出错误格式，尝试提取值为 True 的键
                    for k, v in fg_sentiment.items():
                        if v is True:
                            target["summary"]["all_labels"].add(str(k))

            if not is_comment:
                # 填充主贴信息
                target["post_content"] = item["content"]
                target["post_analysis"] = analysis
                target["post_author"] = item["author"]
                target["created_at"] = item["created_at"]
                target["images"] = item["image_paths"]
            else:
                # 添加评论
                target["comments"].append({
                    "comment_id": item["comment_id"],
                    "content": item["content"],
                    "author": item["author"],
                    "created_at": item["created_at"],
                    "analysis": analysis
                })

        # 转换 set 为 list 以便序列化
        final_list = []
        for note_id, data in aggregated.items():
            data["summary"]["all_keywords"] = sorted(list(data["summary"]["all_keywords"]))
            data["summary"]["all_visual_objects"] = sorted(list(data["summary"]["all_visual_objects"]))
            data["summary"]["all_labels"] = sorted([str(l) for l in data["summary"]["all_labels"] if l])
            final_list.append(data)

        with open(agg_file, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, ensure_ascii=False, indent=2)
        
        # 如果有日期，备份一份聚合数据
        if data_date:
            history_agg = HISTORICAL_LABELED_DIR / f"aggregated_{data_date}.json"
            with open(history_agg, 'w', encoding='utf-8') as f:
                json.dump(final_list, f, ensure_ascii=False, indent=2)

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
        
        entry = {
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

        # 评论记录不需要 top_id
        if entry["comment_id"] != "0" and "top_id" in entry:
            del entry["top_id"]
            
        return entry
