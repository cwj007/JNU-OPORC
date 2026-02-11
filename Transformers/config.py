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
    torch.backends.cudnn.benchmark = True

# 解决国内网络连接 hf-mirror.com 不稳定的问题
# 优先使用本地缓存，避免每次启动都联网检查模型更新
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

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

# 细粒度情感类别映射 (层级结构)
FINE_GRAINED_SENTIMENT_MAPPING = {
    "正面": ["惊喜", "赞赏", "期待", "愉快"],
    "中性": ["中立"],
    "负面": ["愤怒", "失望", "焦虑", "厌恶", "悲伤"]
}

# 意图类别映射 (层级结构)
INTENT_CATEGORIES_MAPPING = {
    "正面": ["推荐/安利", "炫耀/分享"],
    "中性": ["咨询/询问", "吃瓜/围观", "其他"],
    "负面": ["投诉/反馈", "吐槽/不满"]
}

# 扁平化列表供 Prompt 使用
FINE_GRAINED_SENTIMENT_CATEGORIES = [item for sublist in FINE_GRAINED_SENTIMENT_MAPPING.values() for item in sublist]
INTENT_CATEGORIES = [item for sublist in INTENT_CATEGORIES_MAPPING.values() for item in sublist]

# 提示词：引导模型进行图文消解、情感识别和反讽判定
ANALYSIS_PROMPT = """
你是一个舆情专家。请分析“目标”内容的情感与意图，Context仅作背景参考。

分类标准：
- 正面: 情感[{fg_pos}], 意图[{intent_pos}]
- 中性: 情感[{fg_neu}], 意图[{intent_neu}]
- 负面: 情感[{fg_neg}], 意图[{intent_neg}]

核心约束：
1. 情感/意图必须选自对应主类别的列表。
2. 图文矛盾则 irony_detected=true。
3. 无图时 objects=[]，ocr_text=""，reasoning严禁提及图片。
4. 仅输出 JSON，严禁其他文字。

字段要求：
- sentiment: 正面/中性/负面
- fine_grained_sentiment: 细粒度标签
- intent: 意图标签
- irony_detected: true/false
- reasoning: 简短理由(区分背景与目标)
- keywords: 关键词列表
- objects: 视觉对象列表
- ocr_text: OCR文字
"""

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
# VLM Generation Parameters
# 极致加速：将最小像素降低，最大像素从 512 降低到 224 (约 200x200 分辨率)
# 对于情感分析和基本的视觉识别，这个分辨率已经足够，但速度会提升非常多
MIN_PIXELS = 128 * 28 * 28
MAX_PIXELS = 224 * 28 * 28  
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True # 开启 cuDNN 加速
