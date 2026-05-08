import asyncio
import json
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from Visualized.api.database import execute_db, query_db
from Visualized.api.alert_engine import AlertEngine
from Visualized.api.risk_assessment import calculate_cri, determine_level, check_veto_rules

async def test_custom_settings():
    print("Starting custom settings test...")
    
    # 1. Prepare test data
    test_article = {
        "title": "测试文章：涉及自定义敏感词",
        "content": "这是一篇测试文章，包含自定义敏感词：特供、内幕。",
        "sentiment": "负面",
        "created_at": "2026-05-04 10:00:00",
        "note_id": "test_note_123"
    }
    test_comments = [
        {"content": "太糟糕了", "sentiment": "负面", "created_at": "2026-05-04 10:05:00"},
        {"content": "完全同意", "sentiment": "负面", "created_at": "2026-05-04 10:10:00"}
    ]
    
    # 2. Test custom weights
    custom_config = {
        "weights": {
            "w1": 0.5, # 文章负面情感权重加大
            "w2": 0.1, 
            "w3": 0.1, 
            "w4": 0.2, 
            "w5": 0.1
        }
    }
    cri_default, _ = calculate_cri(test_article, test_comments)
    cri_custom, _ = calculate_cri(test_article, test_comments, config=custom_config)
    
    print(f"Default CRI: {cri_default}")
    print(f"Custom Weights CRI: {cri_custom}")
    assert cri_default != cri_custom, "CRI should change with different weights"
    
    # 3. Test custom sensitive words
    custom_keywords_config = {
        "sensitive_words": {
            "politics": ["特供", "内幕"],
            "severe": ["特供"]
        }
    }
    
    # Test veto with custom keywords
    veto_default, _, _ = check_veto_rules(test_article, test_comments)
    veto_custom, reason, _ = check_veto_rules(test_article, test_comments, custom_keywords=custom_keywords_config["sensitive_words"])
    
    print(f"Default Veto: {veto_default}")
    print(f"Custom Keywords Veto: {veto_custom} (Reason: {reason})")
    assert veto_default == False, "Default should not trigger veto for '特供'"
    assert veto_custom == True, "Custom should trigger veto for '特供'"
    
    # Test CRI with custom sensitive words
    _, details_default = calculate_cri(test_article, test_comments)
    _, details_custom = calculate_cri(test_article, test_comments, config=custom_keywords_config)
    
    print(f"Default K-Hit: {details_default['k_hit']}")
    print(f"Custom K-Hit: {details_custom['k_hit']}")
    assert details_default['k_hit'] < details_custom['k_hit'], "Keyword hit score should increase with custom sensitive words"

    # 4. Test custom thresholds
    custom_thresholds = {
        "medium": 0.1, # 非常低的阈值
        "orange": 0.2,
        "high": 0.3
    }
    
    level_default, desc_default = determine_level(0.35, 0.3, 0.15)
    level_custom, desc_custom = determine_level(0.35, 0.3, 0.15, custom_thresholds=custom_thresholds)
    
    print(f"Default Level for CRI 0.35: {level_default} ({desc_default})")
    print(f"Custom Level for CRI 0.35: {level_custom} ({desc_custom})")
    assert level_default == "low", "Default level should be low"
    assert level_custom == "high", "Custom level should be high due to low thresholds"

    print("\nAll tests passed!")

if __name__ == "__main__":
    asyncio.run(test_custom_settings())
