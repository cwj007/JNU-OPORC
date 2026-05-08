
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from Transformers.processors.exporter import Exporter
from Transformers.config import TRANSFORMERS_OUTPUT_DIR, HISTORICAL_LABELED_DIR
from Transformers import utils

def test_aggregation():
    output_file = TRANSFORMERS_OUTPUT_DIR / "test_labeled.jsonl"
    exporter = Exporter(str(output_file))
    
    # Mock data: 1 post + 2 comments
    mock_data = [
        {
            "note_id": "POST1",
            "comment_id": "0",
            "type": "post",
            "content": "This is a great product!",
            "author": "Alice",
            "images": ["img1.jpg"],
            "analysis": {
                "sentiment": "正面",
                "keywords": ["great", "product"],
                "objects": ["box"]
            },
            "data_date": "2026-02-09"
        },
        {
            "note_id": "POST1",
            "comment_id": "C1",
            "type": "comment",
            "content": "I agree!",
            "author": "Bob",
            "analysis": {
                "sentiment": "正面",
                "keywords": ["agree"],
                "objects": []
            }
        },
        {
            "note_id": "POST1",
            "comment_id": "C2",
            "type": "comment",
            "content": "It's okay.",
            "author": "Charlie",
            "analysis": {
                "sentiment": "中性",
                "keywords": ["okay"],
                "objects": []
            }
        }
    ]
    
    utils.logger.info("[test_exporter.test_aggregation] Exporting mock data...")
    exporter.export(mock_data)
    
    agg_file = TRANSFORMERS_OUTPUT_DIR / "aggregated_display_data.json"
    if agg_file.exists():
        with open(agg_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            utils.logger.info("\n[test_exporter.test_aggregation] Aggregated Data Structure:")
            # utils.logger.info(json.dumps(data, indent=2, ensure_ascii=False))
            
            # Verify aggregation
            # Find the item with note_id "POST1"
            item = next((d for d in data if d['note_id'] == "POST1"), None)
            if item:
                assert item['note_id'] == "POST1"
                assert len(item['comments']) >= 2
                assert "great" in item['summary']['all_keywords']
                assert "agree" in item['summary']['all_keywords']
                utils.logger.info("\n[test_exporter.test_aggregation] [Success] Aggregation test passed!")
            else:
                utils.logger.error("\n[test_exporter.test_aggregation] [Error] POST1 not found in aggregated data!")
    else:
        utils.logger.error("\n[test_exporter.test_aggregation] [Error] Aggregated file not found!")


if __name__ == "__main__":
    test_aggregation()
