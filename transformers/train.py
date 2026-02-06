import os

# 设置 Hugging Face 镜像，解决国内网络连接问题
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 禁用 SSL 验证，解决部分网络环境下的 SSL ConnectError
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["PYTHONHTTPSVERIFY"] = "0"

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torch.optim import AdamW
from transformers import BertTokenizer, ViTImageProcessor
from utils.dataset import WeiboDataset
from models.multimodal_model import MultimodalSentimentModel
import os

def train():
    # 1. Setup paths and hyperparameters
    data_dir = r"e:\JNU-OPORC\MediaCrawler\data\weibo\json"
    image_dir = r"e:\JNU-OPORC\MediaCrawler\data\weibo\images"
    batch_size = 8
    epochs = 10
    learning_rate = 2e-5
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 2. Initialize Tokenizer and Processor with retry
    max_retries = 3
    for attempt in range(max_retries):
        try:
            tokenizer = BertTokenizer.from_pretrained("hfl/chinese-roberta-wwm-ext")
            processor = ViTImageProcessor.from_pretrained("google/vit-base-patch16-224")
            # 3. Initialize Model
            model = MultimodalSentimentModel().to(device)
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                import time
                time.sleep(5)
            else:
                raise e

    # 4. Create Dataset and Dataloader
    dataset = WeiboDataset(data_dir, image_dir, tokenizer=tokenizer, processor=processor)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = AdamW(model.parameters(), lr=learning_rate)
    criterion = nn.CrossEntropyLoss()

    # 5. Training Loop
    model.train()
    for epoch in range(epochs):
        total_loss = 0
        for batch in dataloader:
            # Prepare inputs
            text_inputs = batch["text_inputs"]
            input_ids = text_inputs["input_ids"].squeeze(1).to(device)
            attention_mask = text_inputs["attention_mask"].squeeze(1).to(device)
            
            pixel_values = None
            if batch["has_image"].any():
                pixel_values = batch["image_inputs"]["pixel_values"].squeeze(1).to(device)

            # Labels (Placeholder: in a real scenario, you need labeled data)
            # For now, let's assume we have labels in the dataset
            # labels_sentiment = batch["sentiment_labels"].to(device)
            # labels_intent = batch["intent_labels"].to(device)
            # labels_irony = batch["irony_labels"].to(device)

            optimizer.zero_grad()
            
            # Forward pass
            outputs = model(input_ids, attention_mask, pixel_values)
            
            # Loss calculation (Example with placeholders)
            # loss_s = criterion(outputs["sentiment"], labels_sentiment)
            # loss_i = criterion(outputs["intent"], labels_intent)
            # loss_irony = criterion(outputs["irony"], labels_irony)
            # loss = loss_s + loss_i + loss_irony
            
            # For demonstration, we just do a dummy backward if we had labels
            # loss.backward()
            # optimizer.step()
            # total_loss += loss.item()

        print(f"Epoch {epoch+1}/{epochs} finished")

if __name__ == "__main__":
    train()
