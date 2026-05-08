import os
import sys

# 必须在导入任何 AI 库之前设置
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
# 启用显存碎片化管理，这在 6G 显存上至关重要
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

print(">>> [Trainer] Process started, loading torch...")
import torch
print(f">>> [Trainer] Torch loaded (v{torch.version.__version__}). Loading transformers...")
from transformers import Trainer, TrainingArguments, DataCollatorForLanguageModeling
print(">>> [Trainer] Transformers loaded. Adding paths...")

# 自动识别项目根目录
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Transformers.config import TRANSFORMERS_OUTPUT_DIR, LABELED_DATA_FILE

def train_vlm(
    jsonl_path: str,
    output_dir: str = None,
    epochs: int = 3, # 降低轮数，防止训练时间过长
    batch_size: int = 1,
    lr: float = 5e-4, # 暴力提高学习率，强行冲破基础模型偏见
    force_cpu: bool = False, 
):
    """
    Train VLM using LoRA.
    """
    if output_dir is None:
        output_dir = str(TRANSFORMERS_OUTPUT_DIR / "vlm_lora")
        
    print(">>> [Trainer] Initializing components...")
    from Transformers.models.model import MultimodalVLMModel
    from Transformers.models.dataset import MultimodalVLMDataset
    from Transformers import utils
    
    # 1. Initialize Model
    model_wrapper = MultimodalVLMModel(force_cpu=force_cpu)
    model = model_wrapper.model
    tokenizer = model_wrapper.tokenizer if hasattr(model_wrapper, 'tokenizer') else None
    
    # 2. Load Dataset
    dataset = MultimodalVLMDataset(jsonl_path, processor=model_wrapper.processor)
    
    # 3. Training Arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4, # 从 16 降低到 4，加快梯度更新频率
        learning_rate=lr,
        num_train_epochs=epochs,
        logging_steps=5, 
        logging_first_step=True,
        save_strategy="no",
        use_cpu=force_cpu,
        bf16=False,
        fp16=True, 
        optim="paged_adamw_8bit", # 换回分页 8-bit AdamW，利用系统内存做分页缓冲
        remove_unused_columns=False,
        gradient_checkpointing=True, 
        gradient_checkpointing_kwargs={"use_reentrant": False},
        dataloader_num_workers=4, # 增加数据加载线程
        report_to="none"
    )
    
    # 4. Initialize Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False) if tokenizer else None,
    )
    
    # 增加显存清理，确保训练前 GPU 是空的
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        utils.logger.info(f"[trainer.train_vlm] 🧹 Memory cleared. Current VRAM: {torch.cuda.memory_allocated()/1024**2:.1f}MB")
    
    utils.logger.info("[trainer.train_vlm] 🚀 Starting VLM LoRA training...")
    
    # 为了解决 CVE-2025-32434 安全限制，我们暂时跳过旧的 .pt 权重加载，强制重新开始
    resume_checkpoint = None
    utils.logger.info("[trainer.train_vlm] 🛡️ Secure mode: Starting training from scratch to avoid torch.load vulnerabilities.")
    
    trainer.train(resume_from_checkpoint=None)
    utils.logger.info("[trainer.train_vlm] 🏁 Training loop finished! Entering saving phase...")
    
    # 5. Save Model
    utils.logger.info(f"[trainer.train_vlm] 💾 Saving final model weights and processor to {output_dir}...")
    
    # 针对 Windows 和 4-bit 模型的优化保存方式
    if hasattr(model, "save_pretrained"):
        # 只保存 LoRA 适配器和必要的配置文件，避免卡死在全量保存上
        model.save_pretrained(output_dir)
        if model_wrapper.processor:
            model_wrapper.processor.save_pretrained(output_dir)
    else:
        trainer.save_model(output_dir)
        
    utils.logger.info(f"[trainer.train_vlm] ✅ Training complete! Model saved to {output_dir}")

if __name__ == "__main__":
    if os.path.exists(LABELED_DATA_FILE):
        train_vlm(str(LABELED_DATA_FILE))
    else:
        utils.logger.error(f"[trainer.main] Labeled data not found at {LABELED_DATA_FILE}")
