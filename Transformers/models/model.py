import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from .config import VLM_MODEL_ID, MODEL_WEIGHTS_DIR, DEVICE

class MultimodalVLMModel:
    def __init__(self):
        print(f"Loading model for training on {DEVICE}...")
        
        # 1. Load Processor
        self.processor = AutoProcessor.from_pretrained(
            VLM_MODEL_ID,
            cache_dir=str(MODEL_WEIGHTS_DIR),
            trust_remote_code=True
        )
        self.tokenizer = self.processor.tokenizer

        # 2. Load Model with 4-bit Quantization for memory efficiency
        from transformers import BitsAndBytesConfig
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16
        )

        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            VLM_MODEL_ID,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.float16,
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
