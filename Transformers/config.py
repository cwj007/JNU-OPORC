import os
import torch
import warnings
from pathlib import Path

# 过滤不需要的警告输出
# 1. 忽略 Flash Attention 相关的 UserWarning (Windows 环境下常见)
warnings.filterwarnings("ignore", message=".*Torch was not compiled with flash attention.*")
# 2. 忽略一般的 Transformers/PyTorch 警告
warnings.filterwarnings("ignore", category=UserWarning)
# 3. 忽略 PIL 的 DecompressionBombWarning (处理超大图片时触发)
warnings.filterwarnings("ignore", message=".*DecompressionBombWarning.*")
warnings.filterwarnings("ignore", message=".*could be decompression bomb.*")
# 4. 忽略 Transformers 关于 generation flags 的警告 (do_sample=False 时 top_p 等无效的提示)
warnings.filterwarnings("ignore", message=".*generation flags are not valid.*")

# 配置 Hugging Face 镜像加速，解决国内下载卡顿问题
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 优化显存分配，减少碎片化，适配 6GB 显存
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

# 开启计算加速
if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True  # 开启 cudnn 模式，自动选择最优的算法

# 解决国内网络连接 hf-mirror.com 不稳定的问题
# 默认开启离线模式，如果本地没有模型权重，请先手动下载或临时关闭此开关
os.environ["TRANSFORMERS_OFFLINE"] = os.getenv("TRANSFORMERS_OFFLINE", "1")
os.environ["HF_HUB_OFFLINE"] = os.getenv("HF_HUB_OFFLINE", "1")

# Base paths
BASE_DIR = Path(__file__).parent.parent
MEDIA_CRAWLER_DATA_DIR = BASE_DIR / "MediaCrawler" / "data"

# Model settings
# For 6GB VRAM, we use Qwen2-VL-2B with 4-bit quantization
VLM_MODEL_ID = "qwen/Qwen2-VL-2B-Instruct" 
# 将模型权重存储在项目目录内，避免占用 C 盘空间
MODEL_WEIGHTS_DIR = BASE_DIR / "Transformers" / "model_weights"
os.makedirs(MODEL_WEIGHTS_DIR, exist_ok=True)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
USE_4BIT = True

# Platform mapping (Localization)
PLATFORM_MAP = {
    "weibo": "微博",
    "zhihu": "知乎"
}

PLATFORM_PATHS = {
    "weibo": "data/weibo",
    "zhihu": "data/zhihu"
}

# Sentiment categories
SENTIMENT_CATEGORIES = ["正面", "中性", "负面"]

# 细粒度情感类别参考 (仅作为 Prompt 示例，不限制模型输出)
FINE_GRAINED_SENTIMENT_EXAMPLES = {
    "正面": ["惊喜", "赞赏", "期待", "愉快", "欣慰", "欢喜", "感动"],
    "中性": ["中立", "客观", "围观"],
    "负面": ["愤怒", "失望", "焦虑", "厌恶", "悲伤", "吐槽", "不满", "投诉"]
}

# 意图类别参考 (仅作为 Prompt 示例，不限制模型输出)
INTENT_CATEGORIES_EXAMPLES = {
    "正面": ["推荐/安利", "炫耀/分享", "表达喜爱"],
    "中性": ["咨询/询问", "吃瓜/围观", "日常记录"],
    "负面": ["投诉/反馈", "吐槽/不满", "情绪宣泄"]
}

# 扁平化列表 (用于向后兼容和模糊匹配参考)
FINE_GRAINED_SENTIMENT_CATEGORIES = [item for sublist in FINE_GRAINED_SENTIMENT_EXAMPLES.values() for item in sublist]
INTENT_CATEGORIES = [item for sublist in INTENT_CATEGORIES_EXAMPLES.values() for item in sublist]

# 保持变量名兼容
FINE_GRAINED_SENTIMENT_MAPPING = FINE_GRAINED_SENTIMENT_EXAMPLES
INTENT_CATEGORIES_MAPPING = INTENT_CATEGORIES_EXAMPLES

# 微博提示词：侧重情绪与反讽判定
WEIBO_ANALYSIS_PROMPT = """你是一个专业的**微博多模态舆情专家**。请分析“目标”内容的情感与意图。

### 分类要求：
1. **sentiment**: 必须从 ["正面", "中性", "负面"] 中选一。
2. **fine_grained_sentiment**: 自由发挥，给出最精准的情感标签（1-4个字）。
3. **intent**: 自由发挥，给出最精准的意图标签（1-6个字）。

### 核心指南：
1. **情感一致性**: fine_grained_sentiment 和 intent 必须与 sentiment 的极性保持语义一致。
   - 正面示例: {fg_pos} | {intent_pos}
   - 中性示例: {fg_neu} | {intent_neu}
   - 负面示例: {fg_neg} | {intent_neg}
2. **主体识别与归因 (Subject Identification)**: 
   - **核心任务**: 准确识别谁在对谁说话，谁是情感的发出者，谁是客体。
   - 严禁混淆：如果文本提到“XX很笨”，请确认“XX”是作者本人、平台、还是其他第三方。
   - 示例：在“豆包笨还收费”中，作者是在批评“豆包”这一AI产品，而非进行自我调侃。
3. **图文结合深度分析 (Multimodal Integration)**: 
   - **核心要求**: 如果数据包含图片，`reasoning` 中**必须**包含对视觉内容的简要描述（如：图片展示了XX、画面中出现了XX）。
   - **逻辑链条**: 必须阐明视觉信息如何支撑或补充了文本的情感表达。严禁在有图的情况下仅分析文本。
   - **图文冲突**: 特别注意图文不符的情况，这通常是判定“反讽”的重要依据。
4. **背景权重分配**: 
   - 仅当文本带有明显的嘲讽语气（如“真是一场‘精彩’的表演”且背景为失败）或图文严重冲突时判定为 true。
   - 正常的祝福、期待、客观陈述不属于反讽。
5. **严禁输出数字索引或引导词**，仅输出 JSON。

### 字段要求：
- sentiment: "正面"/"中性"/"负面"
- fine_grained_sentiment: 标签词
- intent: 标签词
- irony_detected: true/false
- reasoning: 深度且合理的分析理由 (建议 50-80 字。必须结合“目标内容”的关键词及**视觉图像内容**，逻辑严密地阐述作者对评价主体的核心态度，严禁使用“该用户表达了...”等泛泛而谈的套话)
- keywords: 关键词列表 (3-5个，必须从“目标内容”中提取，严禁重复，严禁包含背景中的无关词汇)
- objects: 视觉对象列表 (无图则为空 [])
- ocr_text: OCR 文字 (无图则为空 "")

**注意: 必须且仅输出一个合法的 JSON 块，严禁包含任何其他文字。**
"""

# 知乎提示词：侧重观点与逻辑分析
ZHIHU_ANALYSIS_PROMPT = """你是一个专业的**知乎多模态舆情专家**。请分析“目标”内容的观点与逻辑。

### 分类要求：
1. **sentiment**: 必须从 ["正面", "中性", "负面"] 中选一。
2. **fine_grained_sentiment**: 自由发挥，给出最精准的情感标签（1-4个字）。
3. **intent**: 自由发挥，给出最精准的意图标签（1-6个字）。

### 核心指南：
1. **情感一致性**: 细粒度标签必须与 sentiment 极性一致。
   - 正面示例: {fg_pos} | {intent_pos}
   - 中性示例: {fg_neu} | {intent_neu}
   - 负面示例: {fg_neg} | {intent_neg}
2. **观点主体归因 (Viewpoint Attribution)**: 
   - 明确区分作者本人的观点与引用的观点。
   - 准确识别评价的对象。
3. **背景与独立判断**: 
   - **上下文/原贴内容**仅供参考，用于理解讨论主题。
   - 目标内容的立场不应被背景强行绑架。负面事件背景下的正面建议、祝福或理性探讨应判定为**正面**或**中性**。
4. **理性优先**: 知乎侧重逻辑分析，严禁输出非 JSON 内容。

### 字段要求：
- sentiment: "正面"/"中性"/"负面"
- fine_grained_sentiment: 标签词
- intent: 标签词
- irony_detected: true/false
- reasoning: 深度且合理的分析理由 (建议 50-80 字。必须结合“目标内容”的观点提炼过程、逻辑链条，并清晰解释判定该情感极性的深层原因)
- keywords: 关键词列表 (3-5个，必须从“目标内容”中提取，严禁重复，严禁包含背景中的无关词汇)
- objects: 视觉对象列表 (无图则为空 [])
- ocr_text: OCR 文字 (无图则为空 "")

**注意: 必须且仅输出一个合法的 JSON 块，严禁包含任何其他文字。**
"""

# 平台提示词映射
PLATFORM_PROMPTS = {
    "weibo": WEIBO_ANALYSIS_PROMPT,
    "zhihu": ZHIHU_ANALYSIS_PROMPT
}

# 保持向后兼容
ANALYSIS_PROMPT = WEIBO_ANALYSIS_PROMPT


# Output settings
TRANSFORMERS_DIR = BASE_DIR / "Transformers"
TRANSFORMERS_OUTPUT_DIR = TRANSFORMERS_DIR / "output"
os.makedirs(TRANSFORMERS_OUTPUT_DIR, exist_ok=True)

# Cache settings
CACHE_DIR = TRANSFORMERS_DIR / "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Input files
def get_weibo_files_by_date(date_str: str):
    """根据日期字符串 (YYYY-MM-DD) 获取对应的微博 CSV 文件路径"""
    from datetime import datetime
    try:
        # 自动标准化日期格式 (例如 2026-2-08 -> 2026-02-08)
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        normalized_date = dt.strftime("%Y-%m-%d")
    except ValueError:
        normalized_date = date_str

    posts_file = MEDIA_CRAWLER_DATA_DIR / "weibo" / "csv" / f"detail_contents_{normalized_date}.csv"
    comments_file = MEDIA_CRAWLER_DATA_DIR / "weibo" / "csv" / f"detail_comments_{normalized_date}.csv"
    return posts_file, comments_file

def get_available_dates():
    """扫描目录获取所有可用的数据日期"""
    csv_dir = MEDIA_CRAWLER_DATA_DIR / "weibo" / "csv"
    if not csv_dir.exists():
        return []
    
    dates = set()
    import re
    date_pattern = re.compile(r"detail_contents_(\d{4}-\d{2}-\d{2})\.csv")
    for f in csv_dir.glob("detail_contents_*.csv"):
        match = date_pattern.search(f.name)
        if match:
            dates.add(match.group(1))
    return sorted(list(dates), reverse=True)

# 默认使用最新日期的文件
available_dates = get_available_dates()
LATEST_DATE = available_dates[0] if available_dates else "2026-02-08"
WEIBO_POSTS_FILE, WEIBO_COMMENTS_FILE = get_weibo_files_by_date(LATEST_DATE)
LABELED_DATA_FILE = TRANSFORMERS_OUTPUT_DIR / "labeled_results.jsonl"
# 历史标注结果存储路径
HISTORICAL_LABELED_DIR = TRANSFORMERS_OUTPUT_DIR / "history"
os.makedirs(HISTORICAL_LABELED_DIR, exist_ok=True)

# Import crawler config for dynamic thresholds
try:
    import sys
    sys.path.append(str(BASE_DIR))
    from MediaCrawler.config.base_config import CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES
except ImportError:
    CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = 100

# Image settings
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
# VLM 能够处理的最大图片数量（建议 1-9 张，过多会导致 OOM 或推理极慢）
MAX_IMAGES_FOR_VLM = 9 
# VLM 最大序列长度 (Tokens)
MAX_SEQ_LENGTH = 2048
# VLM Generation Parameters
# 极致加速：将最小像素降低，最大像素从 512 降低到 168 (约 168x168 分辨率)
# 对于情感分析和基本的视觉识别，这个分辨率已经足够，但速度会提升非常多
MIN_PIXELS = 128 * 28 * 28
MAX_PIXELS = 512 * 28 * 28  
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True # 开启 cuDNN 加速
