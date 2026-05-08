
import json
from Transformers.processors.multimodal_analyzer import MultimodalAnalyzer
from Transformers.models.vlm_handler import VLMHandler

def test_vlm_reasoning():
    # Mock VLM handler
    class MockVLM:
        def analyze(self, *args, **kwargs):
            return ""

    analyzer = MultimodalAnalyzer(MockVLM())
    
    # Test case: Structured reasoning in JSON
    mock_output = """
    ```json
    {
        "sentiment": "负面",
        "fine_grained_sentiment": ["失望", "质疑"],
        "intent": "批评",
        "irony_detected": false,
        "reasoning": {
            "分析目标类型": "评论",
            "分析目标内容": "评论者认为大模型收费不合理，并建议大模型首先做好自己的模型才能考虑收费。",
            "关键词": [
                "大模型收费",
                "大模型收费问题",
                "大模型是否值得收费"
            ]
        },
        "objects": []
    }
    ```
    """
    
    # Parse the output
    result = analyzer._parse_vlm_output(mock_output, has_images=False)
    
    print("Parsed Result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Assertions
    assert isinstance(result["reasoning"], str)
    assert "评论者认为大模型收费不合理" in result["reasoning"]
    assert "大模型收费问题" in result["keywords"]
    assert isinstance(result["fine_grained_sentiment"], list)
    
    # Test case 2: Variation of keys (分析目标内容, 分析目标关键词)
    mock_output_v2 = """
    ```json
    {
        "sentiment": "负面",
        "fine_grained_sentiment": ["失望"],
        "intent": "吐槽",
        "reasoning": {
            "分析目标类型": "评论",
            "分析目标内容": "评论者认为大模型豆包收费是不值得的。",
            "分析目标情绪": "负面",
            "分析目标意图": "吐槽",
            "分析目标关键词": [
                "大模型收费",
                "豆包",
                "用户感知价值"
            ]
        }
    }
    ```
    """
    
    result_v2 = analyzer._parse_vlm_output(mock_output_v2, has_images=False)
    print("\nParsed Result V2:")
    print(json.dumps(result_v2, indent=2, ensure_ascii=False))
    
    assert "评论者认为大模型豆包收费是不值得的" in result_v2["reasoning"]
    assert "用户感知价值" in result_v2["keywords"]
    
    print("\n[Success] VLM reasoning extraction test V2 passed!")

if __name__ == "__main__":
    test_vlm_reasoning()
