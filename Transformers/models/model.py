import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from Transformers.config import VLM_MODEL_ID, MODEL_WEIGHTS_DIR, DEVICE
from Transformers import utils

class MultimodalVLMModel:
    def __init__(self, lora_path=None, force_cpu=False):
        # 强制切换设备
        current_device = "cpu" if force_cpu else DEVICE
        mode = "Inference" if lora_path else "Training"
        utils.logger.info(f"[MultimodalVLMModel.__init__] Loading model for {mode} on {current_device}...")
        
        # 显存限制逻辑仅在 GPU 模式下生效
        max_vram = "3.5GiB"
        
        # 优先使用本地平铺好的权重目录
        import os
        local_flat_path = os.path.join(MODEL_WEIGHTS_DIR, "qwen2vl_2b_4bit")
        
        if os.path.exists(local_flat_path):
            model_to_load = local_flat_path
        else:
            model_to_load = VLM_MODEL_ID
        
        # 1. Load Processor
        self.processor = AutoProcessor.from_pretrained(
            model_to_load,
            cache_dir=str(MODEL_WEIGHTS_DIR),
            trust_remote_code=True,
            local_files_only=True,
            fix_mistral_regex=True
        )
        self.tokenizer = self.processor.tokenizer

        # 2. Load Model
        from transformers import BitsAndBytesConfig
        
        if force_cpu:
            # CPU 模式下不能使用 BitsAndBytes 4-bit 量化加载，需使用 float32 或 bfloat16
            # 但为了节省 RAM，我们尝试使用 float16
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                model_to_load,
                device_map={"": "cpu"},
                dtype=torch.float32, # CPU 训练建议使用 float32 保证稳定
                attn_implementation="eager", # CPU 模式使用基础实现
                cache_dir=str(MODEL_WEIGHTS_DIR),
                trust_remote_code=True,
                local_files_only=True
            )
        else:
            # GPU 4-bit 模式
            has_bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8
            compute_dtype = torch.bfloat16 if has_bf16 else torch.float16
            
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=compute_dtype
            )

            # 针对 Windows "页面文件太小" (OS Error 1455) 的优化
            offload_folder = os.path.join(MODEL_WEIGHTS_DIR, "offload")
            os.makedirs(offload_folder, exist_ok=True)

            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                model_to_load,
                quantization_config=bnb_config,
                device_map="auto",
                dtype=compute_dtype,
                attn_implementation="sdpa",
                cache_dir=str(MODEL_WEIGHTS_DIR),
                trust_remote_code=True,
                local_files_only=True,
                low_cpu_mem_usage=True,
                offload_folder=offload_folder, # 允许权重卸载到磁盘
                max_memory={0: max_vram, "cpu": "8GiB"} # 降低 CPU RAM 预留，缓解 Windows 虚拟内存压力
            )

        # 3. Handle LoRA
        if lora_path and os.path.exists(lora_path):
            from peft import PeftModel
            utils.logger.info(f"[MultimodalVLMModel.__init__] 🎯 Loading trained LoRA adapter from {lora_path}")
            # 推理模式下，我们需要确保是以 4-bit 基础模型加载，然后合并适配器
            self.model = PeftModel.from_pretrained(self.model, lora_path)
            self.model.eval()
        else:
            if not force_cpu:
                self.model = prepare_model_for_kbit_training(self.model)
                # 极致显存优化：冻结视觉编码器 (Visual Tower)
                # 在 6G 显存下，处理图片+文本时，视觉模块的梯度占用是致命的
                if hasattr(self.model, "visual"):
                    utils.logger.info("[MultimodalVLMModel] ❄️ Freezing Visual Tower to save VRAM...")
                    for param in self.model.visual.parameters():
                        param.requires_grad = False
            
            lora_config = LoraConfig(
                r=4, # 极致压缩：Rank 降至 4
                lora_alpha=8,
                target_modules=["q_proj", "v_proj"], # 仅训练最核心的 Q/V 投影
                lora_dropout=0.05,
                bias="none",
                task_type="CAUSAL_LM"
            )
            
            self.model = get_peft_model(self.model, lora_config)
            self.model.print_trainable_parameters()
