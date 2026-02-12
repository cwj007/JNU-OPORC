import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from .config import VLM_MODEL_ID, MODEL_WEIGHTS_DIR, DEVICE
from Transformers import utils

class MultimodalVLMModel:
    def __init__(self):
        utils.logger.info(f"[MultimodalVLMModel.__init__] Loading model for training on {DEVICE}...")
        
        # 1. Load Processor
        self.processor = AutoProcessor.from_pretrained(
            VLM_MODEL_ID,
            cache_dir=str(MODEL_WEIGHTS_DIR),
            trust_remote_code=True
        )
        self.tokenizer = self.processor.tokenizer

        # 2. Load Model with 4-bit Quantization for memory efficiency
        from transformers import BitsAndBytesConfig
        
        # Check for bf16 support (Ampere or newer)
        has_bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8
        compute_dtype = torch.bfloat16 if has_bf16 else torch.float16
        
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype
        )

        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            VLM_MODEL_ID,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=compute_dtype,
            attn_implementation="sdpa", # Use SDPA for speed
            cache_dir=str(MODEL_WEIGHTS_DIR),
            trust_remote_code=True
        )

        # 3. Prepare for LoRA training
        self.model = prepare_model_for_kbit_training(self.model)
        
        lora_config = LoraConfig(
            r=16,
            lora_alpha=32,
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM"
        )
        
        self.model = get_peft_model(self.model, lora_config)
        self.model.print_trainable_parameters()
