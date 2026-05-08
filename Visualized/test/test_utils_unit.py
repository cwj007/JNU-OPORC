# 这是一个单元测试文件（用于测试 Visualized/api/utils.py 中的工具函数）
import sys
import os

# 将项目根目录添加到路径中
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from Visualized.api.utils import contains_chinese, is_junk_label

def test_contains_chinese():
    # 测试用例：包含中文
    assert contains_chinese("你好") == True
    # 测试用例：不包含中文
    assert contains_chinese("Hello") == False
    # 测试用例：混合
    assert contains_chinese("Hello 你好") == True
    # 测试用例：空
    assert contains_chinese("") == False
    # 测试用例：None
    assert contains_chinese(None) == False

def test_is_junk_label():
    # 测试用例：垃圾标签
    assert is_junk_label("unknown") == True
    assert is_junk_label("12345") == True
    assert is_junk_label("abc") == True
    # 测试用例：有效标签
    assert is_junk_label("舆情分析") == False
    assert is_junk_label("Hot Topic") == True  # 默认不包含中文被视为垃圾
    # 测试用例：混合有效
    assert is_junk_label("AI 智能") == False

if __name__ == "__main__":
    try:
        test_contains_chinese()
        print("test_contains_chinese: PASSED")
        test_is_junk_label()
        print("test_is_junk_label: PASSED")
    except AssertionError as e:
        print(f"Test FAILED: {e}")
        sys.exit(1)
