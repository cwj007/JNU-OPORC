import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

# --- MediaCrawler 集成相关导入 ---
try:
    from MediaCrawler.api.routers.crawler import router as mc_crawler_router
    from MediaCrawler.api.routers.websocket import router as mc_ws_router
    HAS_MEDIA_CRAWLER = True
except ImportError as e:
    print(f"Warning: MediaCrawler module not found for integration: {e}")
    HAS_MEDIA_CRAWLER = False

from Transformers.config import (
    MEDIA_CRAWLER_DATA_DIR
)
from Visualized.api.database import init_db, CACHE_DIR as VISUALIZED_CACHE_DIR
from Visualized.api.dashboard import router as dashboard_router
from Visualized.api.monitoring import router as monitoring_router
from Visualized.api.alerts import router as alerts_router
from Visualized.api.config import router as config_router
from Visualized.api.hotsearch import router as hotsearch_router, check_and_sync_missing_data, start_periodic_sync
from Visualized.api.rank import router as rank_router
import asyncio

app = FastAPI(title="JNU-OPORC 舆情监测系统 API")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for images
if MEDIA_CRAWLER_DATA_DIR.exists():
    app.mount("/media", StaticFiles(directory=str(MEDIA_CRAWLER_DATA_DIR)), name="media")

LOGOS_DIR = Path(r"e:\JNU-OPORC\Visualized\logos")
if LOGOS_DIR.exists():
    app.mount("/logos", StaticFiles(directory=str(LOGOS_DIR)), name="logos")

# Templates
templates = Jinja2Templates(directory=str(BASE_DIR / "Visualized" / "templates"))

# 初始化数据库
init_db()

# 启动时检查并补全热搜数据
@app.on_event("startup")
async def startup_event():
    # 1. 检查缺失数据
    try:
        check_and_sync_missing_data()
    except Exception as e:
        print(f"Error during initial data check: {e}")
    
    # 2. 启动后台定时同步任务
    asyncio.create_task(start_periodic_sync())

# --- 挂载 API 路由 ---
app.include_router(dashboard_router, prefix="/api")
app.include_router(monitoring_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(hotsearch_router, prefix="/api")
app.include_router(rank_router, prefix="/api")

# --- 挂载爬虫路由 ---
if HAS_MEDIA_CRAWLER:
    app.include_router(mc_crawler_router, prefix="/api")
    app.include_router(mc_ws_router, prefix="/api")

# --- 路由补丁 (修复 IDE 预览产生的 404) ---
@app.get("/@vite/client")
async def vite_client():
    return JSONResponse(content={})

@app.get("/favicon.ico")
async def favicon():
    return FileResponse(str(BASE_DIR / "Visualized" / "static" / "favicon.ico")) if (BASE_DIR / "Visualized" / "static" / "favicon.ico").exists() else JSONResponse(content={})

# --- 页面路由 ---
@app.get("/")
async def index():
    return FileResponse(str(BASE_DIR / "Visualized" / "templates" / "index.html"))

@app.get("/detail/{note_id}")
async def detail_page(note_id: str):
    return FileResponse(str(BASE_DIR / "Visualized" / "templates" / "detail.html"))

@app.get("/crawler")
async def crawler_page():
    return FileResponse(str(BASE_DIR / "Visualized" / "templates" / "crawler.html"))

@app.get("/hotsearch")
async def hotsearch_page():
    return FileResponse(str(BASE_DIR / "Visualized" / "templates" / "hotsearch.html"))

@app.get("/volume_rank")
async def volume_rank_page():
    return FileResponse(str(BASE_DIR / "Visualized" / "templates" / "volume_rank.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
