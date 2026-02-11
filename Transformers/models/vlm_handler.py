import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
from typing import List, Dict, Any, Optional
from ..config import (
    VLM_MODEL_ID, MODEL_WEIGHTS_DIR, MIN_PIXELS, MAX_PIXELS, 
    SENTIMENT_CATEGORIES, FINE_GRAINED_SENTIMENT_CATEGORIES, INTENT_CATEGORIES,
    FINE_GRAINED_SENTIMENT_MAPPING, INTENT_CATEGORIES_MAPPING,
    DEVICE, USE_4BIT
)

class VLMHandler:
    def __init__(self):
        """初始化 VLM Handler (延迟加载模型)。"""
        self.model = None
        self.processor = None

    def _ensure_loaded(self):
        """确保模型和处理器已加载。"""
        if self.model is not None:
            return

        print(f"正在加载 Qwen2-VL 模型 (目录: {MODEL_WEIGHTS_DIR})...")
        
        load_params = {
            "pretrained_model_name_or_path": VLM_MODEL_ID,
            "cache_dir": str(MODEL_WEIGHTS_DIR),
            "trust_remote_code": True,
            "local_files_only": True  # 默认优先使用本地文件，避免联网超时
        }

        # 尝试使用 Flash Attention 2
        try:
            import flash_attn
            load_params["attn_implementation"] = "flash_attention_2"
        except ImportError:
            load_params["attn_implementation"] = "sdpa"

        if DEVICE == "cuda" and USE_4BIT:
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
            load_params.update({
                "device_map": DEVICE,
                "torch_dtype": torch.float32 if DEVICE == "cpu" else torch.float16
            })

        try:
            # 尝试加载
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(**load_params)
            self.processor = AutoProcessor.from_pretrained(
                VLM_MODEL_ID,
                cache_dir=str(MODEL_WEIGHTS_DIR),
                min_pixels=MIN_PIXELS,
                max_pixels=MAX_PIXELS,
                local_files_only=True
            )
        except Exception as e:
            if "local_files_only" in str(e) or "not found" in str(e).lower():
                print("\n[提示] 本地未检测到模型文件，正在尝试联网下载（请确保网络可访问 hf-mirror.com）...")
                # 禁用离线模式进行下载
                import os
                old_tf_offline = os.environ.get("TRANSFORMERS_OFFLINE")
                old_hf_offline = os.environ.get("HF_HUB_OFFLINE")
                os.environ["TRANSFORMERS_OFFLINE"] = "0"
                os.environ["HF_HUB_OFFLINE"] = "0"
                
                load_params["local_files_only"] = False
                self.model = Qwen2VLForConditionalGeneration.from_pretrained(**load_params)
                self.processor = AutoProcessor.from_pretrained(
                    VLM_MODEL_ID,
                    cache_dir=str(MODEL_WEIGHTS_DIR),
                    min_pixels=MIN_PIXELS,
                    max_pixels=MAX_PIXELS,
                    local_files_only=False
                )
                
                # 恢复离线模式
                if old_tf_offline: os.environ["TRANSFORMERS_OFFLINE"] = old_tf_offline
                if old_hf_offline: os.environ["HF_HUB_OFFLINE"] = old_hf_offline
            else:
                raise e

        print(f"模型加载完成。(像素限制: {MIN_PIXELS} ~ {MAX_PIXELS})")

    def preprocess_batch(self, batch_data: List[Dict[str, Any]], prompt_template: str) -> Dict[str, Any]:
        """对批次数据进行预处理（编码），可在后台线程执行。"""
        if not batch_data:
            return {}
            
        self._ensure_loaded()
        
        # 检查批次是否包含图像
        has_vision = any(item.get("images") for item in batch_data)
        mode = "多模态" if has_vision else "纯文本"
        print(f"    └─ [CPU] 编码模式: {mode}")
        
        # 准备统一的 Prompt 选项，注入层级约束
        prompt_base = prompt_template.format(
            fg_pos=", ".join(FINE_GRAINED_SENTIMENT_MAPPING["正面"]),
            intent_pos=", ".join(INTENT_CATEGORIES_MAPPING["正面"]),
            fg_neu=", ".join(FINE_GRAINED_SENTIMENT_MAPPING["中性"]),
            intent_neu=", ".join(INTENT_CATEGORIES_MAPPING["中性"]),
            fg_neg=", ".join(FINE_GRAINED_SENTIMENT_MAPPING["负面"]),
            intent_neg=", ".join(INTENT_CATEGORIES_MAPPING["负面"])
        )

        batch_messages = []
        for item in batch_data:
            text = item.get("prompt_text", "")
            image_paths = item.get("images", [])
            
            content = []
            for img_path in image_paths:
                content.append({
                    "type": "image",
                    "image": f"file://{img_path}" if not str(img_path).startswith("file://") else img_path,
                    "min_pixels": MIN_PIXELS,
                    "max_pixels": MAX_PIXELS,
                })
            
            # 优化：如果是纯文本，直接拼接 prompt，减少嵌套层级
            if not image_paths:
                content.append({"type": "text", "text": f"{prompt_base}\n\n内容文本: {text}"})
            else:
                content.append({"type": "text", "text": f"{prompt_base}\n\n内容文本: {text}"})
            
            batch_messages.append([{"role": "user", "content": content}])

        # 优化：针对纯文本，跳过 vision 相关的 process_vision_info
        if not has_vision:
            text_prompts = [self.processor.apply_chat_template(msg, tokenize=False, add_generation_prompt=True) for msg in batch_messages]
            inputs = self.processor(
                text=text_prompts,
                padding=True,
                return_tensors="pt",
            )
        else:
            text_prompts = [self.processor.apply_chat_template(msg, tokenize=False, add_generation_prompt=True) for msg in batch_messages]
            image_inputs, video_inputs = process_vision_info(batch_messages)
            inputs = self.processor(
                text=text_prompts,
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            )
        return inputs

    def analyze_batch(self, batch_data: List[Dict[str, Any]], prompt_template: str, preprocessed_inputs: Optional[Dict[str, Any]] = None) -> List[str]:
        """批量分析。支持传入预处理好的 inputs。"""
        if not batch_data and not preprocessed_inputs:
            return []
        
        self._ensure_loaded()
        
        # 准备推理前：显存预检查
        if DEVICE == "cuda":
            free_mem, total_mem = torch.cuda.mem_get_info()
            if free_mem / 1024**3 < 0.5:
                torch.cuda.empty_cache()

        if preprocessed_inputs is not None:
            inputs = preprocessed_inputs
        else:
            inputs = self.preprocess_batch(batch_data, prompt_template)

        inputs = inputs.to(self.model.device)

        # 监控显存
        if DEVICE == "cuda":
            allocated = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"  ├─ [GPU] 已分配: {allocated:.2f}GB | 已保留: {reserved:.2f}GB")

        # 推理生成
        print(f"  ├─ [GPU] 正在生成结果...")
        try:
            with torch.no_grad():
                autocast_ctx = torch.amp.autocast(device_type='cuda', enabled=(DEVICE == "cuda"))
                with autocast_ctx:
                    generated_ids = self.model.generate(
                        **inputs,
                        max_new_tokens=320, # 缩短生成长度，直接提升 GPU 速度
                        do_sample=False, 
                        use_cache=True
                    )
            
            print(f"  [推理] 正在解码模型输出...")
            # 裁剪输入部分，只保留生成的回复
            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            
            decoded_results = self.processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )
        except torch.cuda.OutOfMemoryError as e:
            print(f"\n  [❗ 严重警告] 显存溢出 (OOM): {str(e)}")
            print("  原因: 当前批次 (Batch Size) 过大或文本过长，导致显存请求超出 GPU 限制。")
            print("  建议: 请减小 --batch_size 参数，或将纯文本批次进一步降低。")
            if DEVICE == "cuda":
                torch.cuda.empty_cache()
            raise e # 抛出异常让上层处理
        finally:
            # 显式释放大张量，但不立即 empty_cache (避免卡顿)
            if DEVICE == "cuda":
                if 'inputs' in locals(): del inputs
                if 'generated_ids' in locals(): del generated_ids
                if 'generated_ids_trimmed' in locals(): del generated_ids_trimmed
            
        return decoded_results

    def analyze(self, text: str, image_paths: List[str], prompt_template: str) -> str:
        """单条分析。"""
        results = self.analyze_batch([{"prompt_text": text, "images": image_paths}], prompt_template)
        return results[0]
