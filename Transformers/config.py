import os
import torch
from pathlib import Path

# 配置 Hugging Face 镜像加速，解决国内下载卡顿问题
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 优化显存分配，减少碎片化，适配 6GB 显存
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

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
FINE_GRAINED_SENTIMENT_CATEGORIES = ["惊喜", "愤怒", "失望", "中立", "赞赏", "期待", "焦虑", "厌恶", "悲伤", "愉快"]
INTENT_CATEGORIES = ["投诉/反馈", "咨询/询问", "推荐/安利", "炫耀/分享", "吐槽/不满", "吃瓜/围观", "其他"]

# 提示词：引导模型进行图文消解、情感识别和反讽判定
ANALYSIS_PROMPT = """
你是一个社交媒体舆情分析专家。请结合图片内容（OCR文字、视觉对象）和文本内容，进行多维度情感分析。

注意：输入可能包含“上下文 (Context)”和“目标 (Target)”。
- “上下文”是原贴内容，仅用于帮助你理解背景。
- “目标”是你需要分析的评论内容。
- 如果“目标”没有自带图片，请不要在 JSON 的 objects 和 ocr_text 中输出上下文图片的分析结果。

要求：
1. 图文矛盾消解：如果图片表达正面但文字表达负面（或反之），请判定是否存在反讽。
2. 情感分类（双层）：
   - 主情感：从 {sentiments} 中选择（正面/中性/负面）。
   - 细粒度情感：从 {fine_grained_sentiments} 中选择最精准的一个（必须是字符串，不要输出对象或列表）。
3. 意图识别：从 {intents} 中选择。
4. 反讽判定：明确判定是否包含反讽（true/false）。
5. 推理过程：简述理由。**注意：如果判定不包含反讽，推理中不要提及“没有反讽”等废话，只描述情感和意图的依据。**

请直接输出 JSON 格式，包含以下字段：
- sentiment: 主情感标签 (正面/中性/负面)
- fine_grained_sentiment: 细粒度情感标签
- intent: 意图标签
- irony_detected: true/false
- reasoning: 推理理由（中文）
- keywords: 关键词列表（中文）
- objects: 仅针对“目标”图片的视觉对象列表（若无图则为空列表 []）
- ocr_text: 仅针对“目标”图片的文字内容（若无图则为空字符串 ""）
"""

# Output settings
TRANSFORMERS_DIR = BASE_DIR / "Transformers"
TRANSFORMERS_OUTPUT_DIR = TRANSFORMERS_DIR / "output"
os.makedirs(TRANSFORMERS_OUTPUT_DIR, exist_ok=True)

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
# 极致加速：将最小像素降低，最大像素从 512 降低到 336 (约 300x300 分辨率)
# 对于情感分析和基本的视觉识别，这个分辨率已经足够，但速度会提升非常多
MIN_PIXELS = 128 * 28 * 28
MAX_PIXELS = 336 * 28 * 28  
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True # 开启 cuDNN 加速
