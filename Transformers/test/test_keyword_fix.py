
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from Transformers.processors.multimodal_analyzer import MultimodalAnalyzer
from Transformers.models.vlm_handler import VLMHandler
from Transformers import utils

def test_keyword_deduplication():
    print("Testing keyword deduplication and limiting...")
    utils.logger.info("Testing keyword deduplication and limiting...")
    
    # Mock VLMHandler (don't need actual model loading)
    class MockVLMHandler:
        def __init__(self):
            self.model = None
            
    vlm = MockVLMHandler()
    analyzer = MultimodalAnalyzer(vlm, platform="weibo")
    
    # Simulate a raw output with repeated keywords
    raw_output = """
    ```json
    {
      "sentiment": "负面",
      "fine_grained_sentiment": "愤怒",
      "intent": "反讽",
      "irony_detected": true,
      "reasoning": "测试重复关键词提取",
      "keywords": ["新能源汽车", "中国", "石油", "制裁", "伊朗", "制裁", "制裁", "制裁", "制裁", "制裁", "制裁", "制裁", "制裁", "制裁", "制裁", "制裁", "制裁", "制裁"]
    }
    ```
    """
    
    # Test parsing
    parsed = analyzer._parse_vlm_output(raw_output, has_images=False)
    
    print(f"Parsed keywords: {parsed['keywords']}")
    utils.logger.info(f"Parsed keywords: {parsed['keywords']}")
    
    # Verify deduplication
    assert len(parsed['keywords']) == len(set(parsed['keywords'])), "Keywords are not deduplicated!"
    # Verify limiting (we set limit to 6 in the code)
    assert len(parsed['keywords']) <= 6, f"Keywords limit exceeded: {len(parsed['keywords'])}"
    
    print("Keyword deduplication and limiting test passed!")
    utils.logger.info("Keyword deduplication and limiting test passed!")

def test_context_separation():
    print("\nTesting context vs target prompt construction...")
    utils.logger.info("\nTesting context vs target prompt construction...")
    
    # Mock VLMHandler
    class MockVLMHandler:
        def __init__(self):
            self.model = None
        def analyze(self, text, images, prompt):
            # We just want to see the 'text' passed here
            self.last_text = text
            return json.dumps({
                "sentiment": "正面",
                "fine_grained_sentiment": "赞赏",
                "intent": "表达喜爱",
                "irony_detected": False,
                "reasoning": "测试",
                "keywords": ["测试"]
            })
            
    vlm = MockVLMHandler()
    analyzer = MultimodalAnalyzer(vlm, platform="weibo")
    
    item = {
        "type": "comment",
        "content": "这条评论是目标内容",
        "parent_content": "这是原贴背景内容",
        "images": []
    }
    
    analyzer.analyze_item(item)
    
    print(f"Constructed prompt text:\n{vlm.last_text}")
    utils.logger.info(f"Constructed prompt text:\n{vlm.last_text}")
    
    assert "上下文 (Context - 原贴内容):" in vlm.last_text
    assert "目标 (Target - comment内容):" in vlm.last_text
    assert "这是原贴背景内容" in vlm.last_text
    assert "这条评论是目标内容" in vlm.last_text
    
    print("Context separation test passed!")
    utils.logger.info("Context separation test passed!")

if __name__ == "__main__":
    try:
        test_keyword_deduplication()
        test_context_separation()
        utils.logger.info("\nAll keyword fix tests passed!")
    except Exception as e:
        utils.logger.error(f"\nTests failed: {e}")
        sys.exit(1)
