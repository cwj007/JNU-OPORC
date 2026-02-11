import json
import torch
from torch.utils.data import Dataset
from PIL import Image
from pathlib import Path
from qwen_vl_utils import process_vision_info
from .config import (
    ANALYSIS_PROMPT, SENTIMENT_CATEGORIES, INTENT_CATEGORIES, 
    MIN_PIXELS, MAX_PIXELS, FINE_GRAINED_SENTIMENT_MAPPING, 
    INTENT_CATEGORIES_MAPPING
)

class MultimodalVLMDataset(Dataset):
    def __init__(self, jsonl_path, tokenizer=None, processor=None):
        self.data = []
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                self.data.append(json.loads(line))
        self.tokenizer = tokenizer
        self.processor = processor

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        
        # 准备分析提示词
        prompt = ANALYSIS_PROMPT.format(
            fg_pos=", ".join(FINE_GRAINED_SENTIMENT_MAPPING["正面"]),
            intent_pos=", ".join(INTENT_CATEGORIES_MAPPING["正面"]),
            fg_neu=", ".join(FINE_GRAINED_SENTIMENT_MAPPING["中性"]),
            intent_neu=", ".join(INTENT_CATEGORIES_MAPPING["中性"]),
            fg_neg=", ".join(FINE_GRAINED_SENTIMENT_MAPPING["负面"]),
            intent_neg=", ".join(INTENT_CATEGORIES_MAPPING["负面"])
        )
        
        content = []
        # 添加图片信息
        images = item.get("image_paths", [])
        for img_path in images:
            # 确保路径是绝对路径
            full_path = Path("e:/JNU-OPORC/MediaCrawler") / img_path
            if full_path.exists():
                content.append({
                    "type": "image",
                    "image": str(full_path),
                    "min_pixels": MIN_PIXELS,
                    "max_pixels": MAX_PIXELS,
                })

        # 添加文本信息
        text_content = item.get("content", "")
        content.append({"type": "text", "text": f"{prompt}\n\n内容文本: {text_content}"})

        # 准备目标输出 (JSON 格式)
        sentiment_analysis = item.get("sentiment_analysis", {})
        target_output = json.dumps(sentiment_analysis, ensure_ascii=False)

        messages = [
            {"role": "user", "content": content},
            {"role": "assistant", "content": [{"type": "text", "text": target_output}]}
        ]

        # 使用 processor 处理
        text_prompt = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        image_inputs, video_inputs = process_vision_info(messages)
        
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        # 移除 batch 维度
        return {k: v.squeeze(0) for k, v in inputs.items()}
