import torch
import torch.nn as nn
from transformers import BertModel, ViTModel, CLIPModel

class MultimodalSentimentModel(nn.Module):
    def __init__(self, 
                 text_model_name="hfl/chinese-roberta-wwm-ext", 
                 image_model_name="google/vit-base-patch16-224",
                 num_sentiment_classes=6, # e.g., happy, sad, angry, disappointed, surprise, neutral
                 num_intent_classes=4,    # e.g., complaint, consultation, recommendation, other
                 fusion_dim=512):
        super(MultimodalSentimentModel, self).__init__()
        
        # Encoders
        self.text_encoder = BertModel.from_pretrained(text_model_name)
        self.image_encoder = ViTModel.from_pretrained(image_model_name)
        
        text_dim = self.text_encoder.config.hidden_size
        image_dim = self.image_encoder.config.hidden_size
        
        # Fusion Layer (simple concatenation + MLP)
        self.fusion = nn.Sequential(
            nn.Linear(text_dim + image_dim, fusion_dim),
            nn.ReLU(),
            nn.Dropout(0.1)
        )
        
        # Classification Heads
        self.sentiment_head = nn.Linear(fusion_dim, num_sentiment_classes)
        self.intent_head = nn.Linear(fusion_dim, num_intent_classes)
        self.irony_head = nn.Linear(fusion_dim, 2) # Binary: ironic or not
        
    def forward(self, text_input_ids, text_attention_mask, image_pixel_values=None):
        # Text features
        text_outputs = self.text_encoder(input_ids=text_input_ids, attention_mask=text_attention_mask)
        text_feats = text_outputs.pooler_output # [batch_size, text_dim]
        
        # Image features
        if image_pixel_values is not None:
            image_outputs = self.image_encoder(pixel_values=image_pixel_values)
            image_feats = image_outputs.pooler_output # [batch_size, image_dim]
        else:
            # Handle cases with no image (zero padding)
            batch_size = text_feats.shape[0]
            image_feats = torch.zeros(batch_size, self.image_encoder.config.hidden_size).to(text_feats.device)
            
        # Fusion
        combined_feats = torch.cat((text_feats, image_feats), dim=1)
        fused_feats = self.fusion(combined_feats)
        
        # Outputs
        sentiment_logits = self.sentiment_head(fused_feats)
        intent_logits = self.intent_head(fused_feats)
        irony_logits = self.irony_head(fused_feats)
        
        return {
            "sentiment": sentiment_logits,
            "intent": intent_logits,
            "irony": irony_logits
        }

# For Irony Detection (Contrastive Learning Idea)
# We can also add a "sentiment contrast" loss between text and image encoders 
# during training to help detect when they are inconsistent.
