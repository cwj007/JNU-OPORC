import re

# 辅助函数：判断是否包含中文
def contains_chinese(text):
    if not text: return False
    return bool(re.search(r'[\u4e00-\u9fa5]', str(text)))

# 辅助函数：判断是否仅为数字或英文
def is_junk_label(text):
    if not text: return True
    s = str(text).strip().lower()
    if s in ['unknown', 'none', 'null', '', '控制']: return True
    # 如果不包含中文，且全是数字/英文/符号，则认为是无效标签
    if not contains_chinese(s):
        return True
    return False
