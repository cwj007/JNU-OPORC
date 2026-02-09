import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
from typing import List, Dict, Any, Optional
from ..config import VLM_MODEL_ID, MODEL_WEIGHTS_DIR, MIN_PIXELS, MAX_PIXELS, SENTIMENT_CATEGORIES, FINE_GRAINED_SENTIMENT_CATEGORIES, INTENT_CATEGORIES, DEVICE, USE_4BIT

class VLMHandler:
    def __init__(self):
        """初始化 VLM Handler (延迟加载模型)。"""
        self.model = None
        self.processor = None

    def _ensure_loaded(self):
        """确保模型和处理器已加载。"""
        if self.model is not None:
            return

        print(f"正在从 {MODEL_WEIGHTS_DIR} 加载 Qwen2-VL 模型...")
        print("提示：首次运行或显存不足时，加载过程可能需要 10-30 秒，请耐心等待。")
        
        load_params = {
            "pretrained_model_name_or_path": VLM_MODEL_ID,
            "cache_dir": str(MODEL_WEIGHTS_DIR),
            "trust_remote_code": True
        }

        # 尝试使用 Flash Attention 2
        try:
            import flash_attn
            load_params["attn_implementation"] = "flash_attention_2"
            print("提示：已启用 Flash Attention 2 加速推理。")
        except ImportError:
            # 在 Windows 环境下，Flash Attention 2 较难安装，
            # 默认使用 PyTorch 2.0+ 自带的 SDPA (Scaled Dot Product Attention)，
            # 它会自动调用 Flash Attention 或 Memory Efficient Attention 算子进行加速。
            load_params["attn_implementation"] = "sdpa"
            print("提示：检测到 Windows 环境，已启用 PyTorch 原生 SDPA 内核加速（性能接近 Flash Attention）。")

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
        
        # 加载处理器，并强制限制像素范围以极大提升推理速度
        # min_pixels 设为 128*28*28 (约 100k 像素)，保证能看清 OCR
        # max_pixels 设为 336*28*28 (约 260k 像素)，在 6GB 显存下能显著提速
        self.processor = AutoProcessor.from_pretrained(
            VLM_MODEL_ID,
            cache_dir=str(MODEL_WEIGHTS_DIR),
            min_pixels=MIN_PIXELS,
            max_pixels=MAX_PIXELS
        )
        print(f"模型加载完成。(像素限制: {MIN_PIXELS} ~ {MAX_PIXELS})")

    def preprocess_batch(self, batch_data: List[Dict[str, Any]], prompt_template: str) -> Dict[str, Any]:
        """对批次数据进行预处理（编码），可在后台线程执行。"""
        if not batch_data:
            return {}
            
        self._ensure_loaded()
        
        # 准备统一的 Prompt 选项
        prompt_base = prompt_template.format(
            sentiments=", ".join(SENTIMENT_CATEGORIES),
            fine_grained_sentiments=", ".join(FINE_GRAINED_SENTIMENT_CATEGORIES),
            intents=", ".join(INTENT_CATEGORIES)
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
            content.append({"type": "text", "text": f"{prompt_base}\n\n内容文本: {text}"})
            batch_messages.append([{"role": "user", "content": content}])

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
            # 如果没有预处理好的，则现场处理
            inputs = self.preprocess_batch(batch_data, prompt_template)

        print(f"  [推理] 正在将数据搬运至 GPU...")
        inputs = inputs.to(self.model.device)

        # 监控显存
        if DEVICE == "cuda":
            allocated = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"  [GPU 状态] 批次大小: {len(batch_data)} | 已分配: {allocated:.2f}GB, 已保留: {reserved:.2f}GB")

        # 推理生成
        print(f"  [推理] GPU 正在生成分析结果 (这可能需要一些时间)...")
        try:
            with torch.no_grad():
                autocast_ctx = torch.amp.autocast(device_type='cuda', enabled=(DEVICE == "cuda"))
                with autocast_ctx:
                    generated_ids = self.model.generate(
                        **inputs,
                        max_new_tokens=512,
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
            print(f"\n  [警告] 显存溢出 (OOM): {str(e)}")
            print("  尝试清理显存并建议减小 batch_size 或图片数量。")
            if DEVICE == "cuda":
                torch.cuda.empty_cache()
            raise e
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
