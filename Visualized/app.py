import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Sentiment Analysis Visualization")

from Transformers.config import TRANSFORMERS_DIR, MEDIA_CRAWLER_DATA_DIR, HISTORICAL_LABELED_DIR, get_available_dates, get_weibo_files_by_date
from Transformers.processors.data_manager import DataManager

app = FastAPI(title="Sentiment Analysis Visualization")
data_manager = DataManager()

# Base directories
BASE_DIR = Path(__file__).parent.parent
VISUALIZED_DIR = BASE_DIR / "Visualized"
OUTPUT_FILE = TRANSFORMERS_DIR / "output" / "labeled_results.jsonl"

# Mount static files for images
if MEDIA_CRAWLER_DATA_DIR.exists():
    app.mount("/media", StaticFiles(directory=str(MEDIA_CRAWLER_DATA_DIR)), name="media")

# Templates
templates = Jinja2Templates(directory=str(VISUALIZED_DIR / "templates"))

def load_results(date_str: str = None):
    """加载标注结果，如果提供 date_str，则加载历史结果"""
    target_file = OUTPUT_FILE
    if date_str:
        history_file = HISTORICAL_LABELED_DIR / f"labeled_results_{date_str}.jsonl"
        if history_file.exists():
            target_file = history_file
            
    groups = {}
    if target_file.exists():
        with open(target_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                    nid = item.get("note_id")
                    if nid not in groups:
                        groups[nid] = {"post": None, "comments": []}
                    
                    if item.get("comment_id") == "0":
                        groups[nid]["post"] = item
                    else:
                        groups[nid]["comments"].append(item)
                except:
                    continue
    
    display_groups = []
    for nid, group in groups.items():
        if group["post"] or group["comments"]:
            if not group["post"]:
                group["post"] = group["comments"].pop(0)
            display_groups.append(group)
    
    display_groups.sort(key=lambda x: x["post"].get("created_at", ""), reverse=True)
    return display_groups[:50]  # Limit to 50 latest results for performance

def get_sentiment_trends():
    """计算跨时间维度的情感分布趋势"""
    available_dates = get_available_dates()
    trends = []
    
    for d in sorted(available_dates):
        history_file = HISTORICAL_LABELED_DIR / f"labeled_results_{d}.jsonl"
        # 如果历史文件不存在，尝试读取主结果文件（如果它的日期匹配）
        if not history_file.exists() and d == available_dates[0]:
            history_file = OUTPUT_FILE
            
        if history_file.exists():
            counts = {"正面": 0, "中性": 0, "负面": 0, "total": 0}
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        item = json.loads(line)
                        sent = item.get("sentiment_analysis", {}).get("sentiment")
                        if sent in counts:
                            counts[sent] += 1
                            counts["total"] += 1
                    except: continue
            if counts["total"] > 0:
                trends.append({
                    "date": d,
                    "positive": round(counts["正面"] / counts["total"] * 100, 1),
                    "neutral": round(counts["中性"] / counts["total"] * 100, 1),
                    "negative": round(counts["负面"] / counts["total"] * 100, 1)
                })
    return trends

@app.get("/test-html")
async def test_html():
    return HTMLResponse(content="<h1>Hello World</h1>", status_code=200)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str = None):
    available_dates = get_available_dates()
    current_date = date or (available_dates[0] if available_dates else None)
    
    groups = load_results(date)
    trends = get_sentiment_trends()
    
    print(f"DEBUG: Rendering index with {len(groups)} groups and {len(trends)} trend points.")
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "groups": groups, 
        "available_dates": available_dates,
        "current_date": current_date,
        "trends": trends,
        "post_trends": trends,  # 确保模板中引用的变量存在
        "comment_trends": []    # 暂时传空
    })

@app.get("/diff")
async def diff_data(request: Request, date1: str, date2: str):
    """对比两个日期的数据差异"""
    f1_p, f1_c = get_weibo_files_by_date(date1)
    f2_p, f2_c = get_weibo_files_by_date(date2)
    
    data1 = data_manager.load_weibo_data(str(f1_p), str(f1_c))
    data2 = data_manager.load_weibo_data(str(f2_p), str(f2_c))
    
    diff = data_manager.compare_data(data1, data2)
    return diff

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
