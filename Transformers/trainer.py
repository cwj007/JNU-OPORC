import torch
from transformers import Trainer, TrainingArguments, DataCollatorForLanguageModeling
from .models.model import MultimodalVLMModel
from .models.dataset import MultimodalVLMDataset
from .config import TRANSFORMERS_OUTPUT_DIR
from Transformers import utils

def train_vlm(
    jsonl_path: str,
    output_dir: str = str(TRANSFORMERS_OUTPUT_DIR / "vlm_lora"),
    epochs: int = 3,
    batch_size: int = 1, # Small batch size for 6GB VRAM
    lr: float = 1e-4,
):
    """
    Train VLM using LoRA and 4-bit quantization.
    """
    # 1. Initialize Model
    model_wrapper = MultimodalVLMModel()
    model = model_wrapper.model
    tokenizer = model_wrapper.tokenizer if hasattr(model_wrapper, 'tokenizer') else None
    
    # 2. Load Dataset
    dataset = MultimodalVLMDataset(jsonl_path, processor=model_wrapper.processor)
    
    # 3. Training Arguments
    has_bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8
    
    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=lr,
        num_train_epochs=epochs,
        logging_steps=10,
        save_strategy="epoch",
        bf16=has_bf16,
        fp16=not has_bf16,
        tf32=torch.cuda.is_available(),
        optim="paged_adamw_32bit", # Memory efficient optimizer
        remove_unused_columns=False,
        gradient_checkpointing=True,
        dataloader_num_workers=2,
        report_to="none"
    )
    
    # 4. Initialize Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False) if tokenizer else None,
    )
    
    utils.logger.info("[trainer.train_vlm] 🚀 Starting VLM LoRA training...")
    trainer.train()
    
    # 5. Save Model
    trainer.save_model(output_dir)
    utils.logger.info(f"[trainer.train_vlm] ✅ Training complete! Model saved to {output_dir}")

if __name__ == "__main__":
    import os
    from .config import LABELED_DATA_FILE
    if os.path.exists(LABELED_DATA_FILE):
        train_vlm(str(LABELED_DATA_FILE))
    else:
        utils.logger.error(f"[trainer.main] Labeled data not found at {LABELED_DATA_FILE}")
