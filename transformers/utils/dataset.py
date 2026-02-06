import json
import os
import glob
import pandas as pd
from PIL import Image
import torch
from torch.utils.data import Dataset
from typing import List, Dict, Optional

class WeiboDataset(Dataset):
    def __init__(self, data_dir: str, image_dir: str, tokenizer=None, processor=None, max_length=512):
        """
        Args:
            data_dir: Path to the directory containing JSON files (e.g., MediaCrawler/data/weibo/json)
            image_dir: Path to the directory containing images (e.g., MediaCrawler/data/weibo/images)
            tokenizer: Transformers tokenizer for text
            processor: Image processor (e.g., ViTFeatureExtractor or CLIPProcessor)
            max_length: Maximum sequence length for text
        """
        self.data_dir = data_dir
        self.image_dir = image_dir
        self.tokenizer = tokenizer
        self.processor = processor
        self.max_length = max_length
        
        self.data = self._load_data()
        
    def _load_data(self) -> List[Dict]:
        all_data = []
        # Load all content files
        content_files = glob.glob(os.path.join(self.data_dir, "detail_contents_*.json"))
        for file in content_files:
            with open(file, 'r', encoding='utf-8') as f:
                try:
                    items = json.load(f)
                    all_data.extend(items)
                except json.JSONDecodeError:
                    continue
        
        # Load all comment files and link them if needed
        # For now, let's focus on the posts (contents) as the primary multimodal units
        # Comments are usually text-only, but sometimes have images too.
        
        processed_data = []
        for item in all_data:
            # Extract image pids from the 'pictures' field
            pics_str = item.get("pictures", "")
            image_paths = []
            if pics_str:
                urls = pics_str.split(",")
                for url in urls:
                    if not url: continue
                    # Extract pid from URL: https://.../pid.jpg
                    pid = url.split("/")[-1].split(".")[0]
                    # Find local file (might be jpg, png, etc.)
                    possible_paths = glob.glob(os.path.join(self.image_dir, f"{pid}.*"))
                    if possible_paths:
                        image_paths.append(possible_paths[0])
            
            processed_data.append({
                "note_id": str(item.get("note_id", "")),
                "text": item.get("content", ""),
                "images": image_paths,
                "raw_item": item
            })
            
        return processed_data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        text = item["text"]
        image_paths = item["images"]
        
        # Handle images (taking the first image for simplicity in multimodal models)
        if image_paths and self.processor:
            try:
                image = Image.open(image_paths[0]).convert("RGB")
                image_inputs = self.processor(images=image, return_tensors="pt")
                # Remove the batch dimension added by return_tensors="pt"
                for k, v in image_inputs.items():
                    image_inputs[k] = v.squeeze(0)
            except Exception as e:
                print(f"Error loading image {image_paths[0]}: {e}")
                image_inputs = self._get_dummy_image()
        else:
            image_inputs = self._get_dummy_image()
                
        # Handle text
        if self.tokenizer:
            text_inputs = self.tokenizer(
                text, 
                padding='max_length', 
                truncation=True, 
                max_length=self.max_length, 
                return_tensors="pt"
            )
            # Remove the batch dimension
            for k, v in text_inputs.items():
                text_inputs[k] = v.squeeze(0)
        else:
            text_inputs = text

        return {
            "note_id": item["note_id"],
            "text_inputs": text_inputs,
            "image_inputs": image_inputs,
            "has_image": len(image_paths) > 0
        }

    def _get_dummy_image(self) -> Dict[str, torch.Tensor]:
        """Returns a dummy image input (zeros) with the correct shape."""
        # Standard ViT shape: [3, 224, 224]
        return {
            "pixel_values": torch.zeros(3, 224, 224)
        }

if __name__ == "__main__":
    # Test the dataset
    data_path = r"e:\JNU-OPORC\MediaCrawler\data\weibo\json"
    img_path = r"e:\JNU-OPORC\MediaCrawler\data\weibo\images"
    dataset = WeiboDataset(data_path, img_path)
    print(f"Loaded {len(dataset)} items")
    if len(dataset) > 0:
        print(f"First item: {dataset[0]}")
