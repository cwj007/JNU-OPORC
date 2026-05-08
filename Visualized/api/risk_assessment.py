import math
import statistics
import json
from datetime import datetime

# Keyword Definitions (Can be extended or loaded from DB)
CRISIS_KEYWORDS = {
    "politics": ["政治", "政策", "政府", "领土", "外交", "主权", "敏感", "违禁"],
    "law": ["法律", "诉讼", "法院", "判决", "违法", "犯罪", "侵权", "官司", "律师"],
    "ethics": ["伦理", "道德", "歧视", "偏见", "骚扰", "霸凌", "虐待", "造假", "丑闻"],
    "severe": ["杀人", "暴恐", "反动", "炸弹", "自杀", "涉政", "严重谣言", "违法"] # Veto keywords extended
}

def get_sentiment_score(sentiment_val):
    """
    Convert sentiment value to score (0-1).
    Support both string labels and numeric scores.
    '负面' -> 0.9, '中性' -> 0.5, '正面' -> 0.1
    """
    if sentiment_val is None:
        return 0.5
    
    if isinstance(sentiment_val, (int, float)):
        # Assuming 0-1 scale, or -1 to 1? Let's assume 0-1 based on user context
        return float(sentiment_val)
    
    s = str(sentiment_val).strip()
    if s == '负面': return 0.9
    if s == '正面': return 0.1
    if s == '中性': return 0.5
    return 0.5

def check_veto_rules(article, comments, details=None, custom_keywords=None):
    """
    一票否决规则 (兜底逻辑)
    此规则独立于上述 CRI计算，拥有最高优先级。一旦触发，直接定为红色预警。
    
    规则示例：
    1. 识别到违法、涉政暴恐、严重谣言等法律明文禁止内容。
    2. 负面评论比例 C_ratio > 0.95 且 评论总数超过 50条
    3. 疑似机器人刷屏（重复评论 > 80%）
    """
    text = (article.get('title', '') + " " + article.get('content', '')).lower()
    
    # 使用自定义关键词或默认关键词
    severe_keywords = custom_keywords.get("severe", CRISIS_KEYWORDS["severe"]) if custom_keywords else CRISIS_KEYWORDS["severe"]
    
    # 1. 严重违规内容检测
    for word in severe_keywords:
        if word in text:
            return True, f"触发一票否决：检测到严重违规关键词 '{word}'", "red"
            
    # 2. 极端负面舆情检测
    # Use provided details if available, otherwise calculate
    if details:
        c_ratio = details.get('c_ratio', 0)
        total_comments = details.get('total_comments', 0)
    else:
        total_comments = len(comments)
        neg_count = 0
        for c in comments:
             s = c.get('sentiment', '')
             score = get_sentiment_score(s)
             if s == '负面' or score >= 0.6:
                 neg_count += 1
        c_ratio = neg_count / total_comments if total_comments > 0 else 0

    if c_ratio > 0.95 and total_comments > 50:
        return True, f"触发一票否决：评论数{total_comments}且负面占比{c_ratio:.2%} (>95%)", "red"
        
    # 3. Bot detection (Simple check: duplicate comments > 80%)
    if len(comments) > 50:
        comment_texts = [c.get('content', '') for c in comments]
        # Remove empty comments from check
        comment_texts = [t for t in comment_texts if t.strip()]
        if comment_texts:
            unique_comments = set(comment_texts)
            if len(unique_comments) / len(comment_texts) < 0.2: # > 80% duplicates
                return True, "触发一票否决：检测到疑似机器人刷屏（重复评论占比过高）", "red"
            
    return False, None, None

def calculate_cri(article, comments, config=None):
    """
    Calculate Comprehensive Risk Index (CRI) based on user formula:
    CRI = w1*A_neg + w2*C_ratio + w3*C_intensity + w4*K_hit + w5*Burst_factor
    """
    if config is None:
        config = {}
    
    # Weights (Default recommendation)
    weights = config.get('weights', {
        'w1': 0.2, # A_neg: 文章负面情感强度
        'w2': 0.3, # C_ratio: 负面评论比例
        'w3': 0.1, # C_intensity: 负面评论情感强度均值
        'w4': 0.3, # K_hit: 关键词命中惩罚分
        'w5': 0.1  # Burst_factor: 评论爆发系数
    })
    
    # 1. A_neg: Article Negative Sentiment (0-1)
    a_neg = get_sentiment_score(article.get('sentiment', ''))
    
    # 2. C_ratio & 3. C_intensity
    total_comments = len(comments)
    neg_comments = []
    neg_scores = []
    
    for c in comments:
        score = get_sentiment_score(c.get('sentiment', ''))
        if score >= 0.6: # Consider negative threshold (e.g., >0.5 or '负面')
            neg_comments.append(c)
            neg_scores.append(score)
            
    c_ratio = len(neg_comments) / total_comments if total_comments > 0 else 0
    c_intensity = statistics.mean(neg_scores) if neg_scores else 0
    
    # 4. K_hit: Keyword Hit Score (Normalized 0-1)
    # Strategy: Count hits in title and content.
    # Weights: Politics=1.0, Law=0.8, Ethics=0.6 per hit? Or just binary presence?
    # User says: "Based on number of hits and level".
    # Simple implementation: 
    #   High risk words (politics) = 0.5 per hit
    #   Medium risk words (law) = 0.3 per hit
    #   Low risk words (ethics) = 0.2 per hit
    #   Cap at 1.0
    text = (article.get('title', '') + " " + article.get('content', '')).lower()
    k_score = 0
    
    # 使用自定义关键词或默认关键词
    custom_keywords = config.get('sensitive_words', {}) if config else {}
    politics_keywords = custom_keywords.get("politics", CRISIS_KEYWORDS["politics"])
    law_keywords = custom_keywords.get("law", CRISIS_KEYWORDS["law"])
    ethics_keywords = custom_keywords.get("ethics", CRISIS_KEYWORDS["ethics"])
    
    for word in politics_keywords:
        if word in text: k_score += 0.5
    for word in law_keywords:
        if word in text: k_score += 0.3
    for word in ethics_keywords:
        if word in text: k_score += 0.2
        
    k_hit = min(k_score, 1.0) # Cap at 1.0
    
    # 5. Burst_factor: Comment Burst (Normalized 0-1)
    # Formula: Comments per hour since post.
    # To normalize 0-1, we need a reference max burst (e.g., 100 comments/hour = 1.0).
    try:
        created_at = datetime.strptime(article.get('created_at', ''), "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        hours_diff = (now - created_at).total_seconds() / 3600
        if hours_diff < 0.1: hours_diff = 0.1 # Avoid division by zero
        
        burst_rate = total_comments / hours_diff
        # Assume 50 comments/hour is "High Burst" (1.0)
        burst_factor = min(burst_rate / 50.0, 1.0)
    except:
        burst_factor = 0
    
    # Calculate CRI with dynamic weight redistribution if no comments
    total_comments = len(comments)
    if total_comments == 0:
        # Redistribution: If no comments, weights are shifted to article sentiment and keyword hits
        # Current applicable weights: w1 (0.2) + w4 (0.3) = 0.5
        # Normalized: w1_norm = 0.2/0.5 = 0.4, w4_norm = 0.3/0.5 = 0.6
        w_sum = weights['w1'] + weights['w4']
        w1_norm = weights['w1'] / w_sum if w_sum > 0 else 1.0
        w4_norm = weights['w4'] / w_sum if w_sum > 0 else 0.0
        
        cri = (w1_norm * a_neg + w4_norm * k_hit)
        c_ratio = 0
        c_intensity = 0
        burst_factor = 0
    else:
        # Standard calculation with comments
        cri = (weights['w1'] * a_neg + 
               weights['w2'] * c_ratio + 
               weights['w3'] * c_intensity + 
               weights['w4'] * k_hit + 
               weights['w5'] * burst_factor)
           
    details = {
        "a_neg": round(a_neg, 2),
        "c_ratio": round(c_ratio, 2),
        "c_intensity": round(c_intensity, 2),
        "k_hit": round(k_hit, 2),
        "burst_factor": round(burst_factor, 2),
        "total_comments": total_comments,
        "negative_comments_count": len(neg_comments),
        "cri": round(cri, 2)
    }
    
    return cri, details

def get_dynamic_threshold(article_group_stats=None):
    """
    Calculate dynamic thresholds based on historical stats (Mean, StdDev).
    For now, use default values if no history provided.
    
    Default for general news: Mean=0.3, StdDev=0.15
    """
    if article_group_stats:
        mu = article_group_stats['mean']
        sigma = article_group_stats['std']
    else:
        # Fallback defaults
        mu = 0.3
        sigma = 0.15
        
    return mu, sigma

def determine_level(cri, mu, sigma, custom_thresholds=None):
    """
    Determine alert level based on CRI and thresholds.
    Adjusted Logic (More lenient):
    Low (Green): CRI < 0.45
    Medium (Yellow): 0.45 <= CRI < 0.60
    High (Orange): 0.60 <= CRI < 0.75
    Critical (Red): CRI >= 0.75
    """
    # Using fixed thresholds as requested by user feedback "all high risk"
    
    # 使用自定义阈值或默认阈值
    thresholds = custom_thresholds or {
        "medium": 0.45,
        "orange": 0.60,
        "high": 0.75
    }
    
    if cri >= thresholds.get("high", 0.75):
        return "high", "高危"  # Map 'red' to 'high' (Critical)
    elif cri >= thresholds.get("orange", 0.60):
        return "orange", "高风险" # (High Risk)
    elif cri >= thresholds.get("medium", 0.45):
        return "medium", "风险显著" # (Medium Risk / Attention)
    else:
        return "low", "正常波动" # (Low Risk / Normal)
