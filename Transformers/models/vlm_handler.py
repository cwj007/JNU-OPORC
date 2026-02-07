import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
from typing import List, Dict, Any, Optional
from ..config import VLM_MODEL_ID, MODEL_WEIGHTS_DIR, MIN_PIXELS, MAX_PIXELS, SENTIMENT_CATEGORIES, INTENT_CATEGORIES, DEVICE, USE_4BIT

class VLMHandler:
    def __init__(self):
        """初始化 VLM 模型。"""
        print(f"正在加载模型（存储路径: {MODEL_WEIGHTS_DIR}）...")
        
        load_params = {
            "pretrained_model_name_or_path": VLM_MODEL_ID,
            "cache_dir": str(MODEL_WEIGHTS_DIR),
            "attn_implementation": "sdpa",
            "low_cpu_mem_usage": True,
            "trust_remote_code": True
        }

        if DEVICE == "cuda" and USE_4BIT:
            print("提示：检测到 GPU，正在进行 4-bit 实时量化加载，这可能需要 2-5 分钟...")
            from transformers import BitsAndBytesConfig
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16
            )
            load_params.update({
                "quantization_config": bnb_config,
                "device_map": "auto",
                "torch_dtype": torch.float16
            })
        else:
            print(f"提示：使用 {DEVICE} 模式加载模型（不使用 4-bit 量化）...")
            load_params.update({
                "device_map": DEVICE,
                "torch_dtype": torch.float32 if DEVICE == "cpu" else torch.float16
            })

        self.model = Qwen2VLForConditionalGeneration.from_pretrained(**load_params)
        self.processor = AutoProcessor.from_pretrained(
            VLM_MODEL_ID,
            cache_dir=str(MODEL_WEIGHTS_DIR) # 指定本地缓存目录
        )

    def analyze(self, text: str, image_paths: List[str], prompt_template: str) -> str:
        """分析文本和图片内容。"""
        # 准备 Prompt，填入分类选项
        prompt = prompt_template.format(
            sentiments=", ".join(SENTIMENT_CATEGORIES),
            intents=", ".join(INTENT_CATEGORIES)
        )

        # 构建对话消息
        content = []
        
        # 添加图片
        for img_path in image_paths:
            content.append({
                "type": "image",
                "image": img_path,
                "min_pixels": MIN_PIXELS,
                "max_pixels": MAX_PIXELS,
            })
            
        # 添加文本
        content.append({"type": "text", "text": f"{prompt}\n\n内容文本: {text}"})

        messages = [{"role": "user", "content": content}]

        # 预处理
        text_prompt = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)

        # 推理生成
        generated_ids = self.model.generate(
            **inputs, 
            max_new_tokens=256,
            do_sample=False,    # 贪婪搜索速度更快
            use_cache=True,     # 确保使用 KV cache
            # 显式设为 None 以消除 do_sample=False 时的警告
            temperature=None,
            top_p=None,
            top_k=None
        )
        
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )

        return output_text[0]
