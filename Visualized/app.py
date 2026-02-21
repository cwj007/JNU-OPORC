import os
import sys
import json
import subprocess
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
    from MediaCrawler.api.routers.data import router as mc_data_router
    HAS_MEDIA_CRAWLER = True
    print("MediaCrawler module loaded successfully")
except ImportError as e:
    import traceback
    traceback.print_exc()
    print(f"Warning: MediaCrawler module not found for integration: {e}")
    HAS_MEDIA_CRAWLER = False

# --- MediaCrawler 额外配置路由 (Config/Env/Health) ---
# 这些路由在 MediaCrawler 的 api/main.py 中直接定义，没有包含在 routers 中
# 我们在这里重新定义它们以确保 Visualized 系统能够提供这些接口

from fastapi import APIRouter
mc_extra_router = APIRouter()

@mc_extra_router.get("/config/platforms")
async def get_mc_platforms():
    """Get list of supported platforms (MediaCrawler)"""
    return {
        "platforms": [
            {"value": "xhs", "label": "Xiaohongshu", "icon": "book-open"},
            {"value": "dy", "label": "Douyin", "icon": "music"},
            {"value": "ks", "label": "Kuaishou", "icon": "video"},
            {"value": "bili", "label": "Bilibili", "icon": "tv"},
            {"value": "wb", "label": "Weibo", "icon": "message-circle"},
            {"value": "tieba", "label": "Baidu Tieba", "icon": "messages-square"},
            {"value": "zhihu", "label": "Zhihu", "icon": "help-circle"},
        ]
    }

@mc_extra_router.get("/config/options")
async def get_mc_config_options():
    """Get all configuration options (MediaCrawler)"""
    return {
        "login_types": [
            {"value": "qrcode", "label": "QR Code Login"},
            {"value": "cookie", "label": "Cookie Login"},
        ],
        "crawler_types": [
            {"value": "search", "label": "Search Mode"},
            {"value": "detail", "label": "Detail Mode"},
            {"value": "creator", "label": "Creator Mode"},
        ],
        "save_options": [
            {"value": "json", "label": "JSON File"},
            {"value": "csv", "label": "CSV File"},
            {"value": "excel", "label": "Excel File"},
            {"value": "sqlite", "label": "SQLite Database"},
            {"value": "db", "label": "MySQL Database"},
            {"value": "mongodb", "label": "MongoDB Database"},
        ],
    }

@mc_extra_router.get("/env/check")
async def check_mc_environment():
    """Check if MediaCrawler environment is configured correctly"""
    try:
        # Run uv run main.py --help command to check environment
        # IMPORTANT: Run in MediaCrawler directory
        mc_dir = BASE_DIR / "MediaCrawler"
        process = await asyncio.create_subprocess_exec(
            "uv", "run", "main.py", "--help",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(mc_dir)  # Run in MediaCrawler directory
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=30.0  # 30 seconds timeout
        )

        if process.returncode == 0:
            return {
                "success": True,
                "message": "MediaCrawler environment configured correctly",
                "output": stdout.decode("utf-8", errors="ignore")[:500]  # Truncate to first 500 characters
            }
        else:
            error_msg = stderr.decode("utf-8", errors="ignore") or stdout.decode("utf-8", errors="ignore")
            return {
                "success": False,
                "message": "Environment check failed",
                "error": error_msg[:500]
            }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": "Environment check timeout",
            "error": "Command execution exceeded 30 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Environment check error",
            "error": str(e)
        }

@mc_extra_router.get("/health")
async def mc_health_check():
    return {"status": "ok"}

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
from Visualized.api.scheduler import router as scheduler_router, start_scheduler
import asyncio

app = FastAPI(title="JNU-OPORC 舆情监测系统 API")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    print(f"Response: {response.status_code}")
    return response

# Mount static files for images
if MEDIA_CRAWLER_DATA_DIR.exists():
    app.mount("/media", StaticFiles(directory=str(MEDIA_CRAWLER_DATA_DIR)), name="media")

LOGOS_DIR = Path(r"e:\JNU-OPORC\Visualized\logos")
if LOGOS_DIR.exists():
    app.mount("/logos", StaticFiles(directory=str(LOGOS_DIR)), name="logos")

STATIC_DIR = Path(r"e:\JNU-OPORC\Visualized\static")
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
    
    # 3. 启动自定义任务调度器 (微博 ID 提取等)
    start_scheduler()

# --- 挂载 API 路由 ---
app.include_router(dashboard_router, prefix="/api")
app.include_router(monitoring_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(hotsearch_router, prefix="/api")
app.include_router(rank_router, prefix="/api")
app.include_router(scheduler_router, prefix="/api")

# --- 挂载 MediaCrawler 静态资源 ---
MC_WEBUI_DIR = BASE_DIR / "MediaCrawler" / "api" / "webui"
if MC_WEBUI_DIR.exists():
    # Mount assets for MediaCrawler UI
    assets_dir = MC_WEBUI_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="mc_assets")

    # Route for serving the MediaCrawler index.html
    @app.get("/mc_ui")
    async def mc_ui():
        index_path = MC_WEBUI_DIR / "index.html"
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Inject script to ensure API requests go to /api prefix
                # This fixes issues where frontend might request /crawler directly or use hardcoded localhost:8080
                injection = """
                <script>
                (function() {
                    console.log("MediaCrawler API Patcher Loaded");
                    const originalFetch = window.fetch;
                    window.fetch = function(url, options) {
                        // Redirect /crawler, /data, /ws requests to /api prefix
                        if (typeof url === 'string') {
                            if (url.startsWith('/crawler') || url.startsWith('/data') || url.startsWith('/ws')) {
                                console.log('Redirecting URL to /api:', url);
                                url = '/api' + url;
                            } else if (url.includes('localhost:8080/crawler') || url.includes('localhost:8080/data')) {
                                // Handle full URLs if present
                                url = url.replace('localhost:8080/', 'localhost:8080/api/');
                                console.log('Rewriting full URL:', url);
                            }
                        }
                        return originalFetch(url, options);
                    };
                })();
                </script>
                """
                content = content.replace("</head>", injection + "</head>")
                return HTMLResponse(content=content)
            except Exception as e:
                print(f"Error serving MediaCrawler UI: {e}")
                return FileResponse(str(index_path))
                
        return JSONResponse(content={"error": "MediaCrawler WebUI not found"}, status_code=404)

    # Route for vite.svg
    @app.get("/vite.svg")
    async def vite_svg():
        svg_path = MC_WEBUI_DIR / "vite.svg"
        if svg_path.exists():
            return FileResponse(str(svg_path))
        return JSONResponse(content={"error": "vite.svg not found"}, status_code=404)

# --- 挂载爬虫路由 ---
if HAS_MEDIA_CRAWLER:
    # Mount at /api prefix (original behavior)
    app.include_router(mc_crawler_router, prefix="/api")
    app.include_router(mc_ws_router, prefix="/api")
    app.include_router(mc_data_router, prefix="/api")

    # Also mount at root level to handle requests that omit /api prefix
    # This ensures frontend calls to /crawler/..., /data/..., /ws/... work correctly
    app.include_router(mc_crawler_router)
    app.include_router(mc_ws_router)
    app.include_router(mc_data_router)

# Mount extra MediaCrawler routers (Config/Env/Health)
# These are safe to mount even if MediaCrawler module import fails, 
# as they don't depend on the module itself, but on the file structure.
app.include_router(mc_extra_router, prefix="/api")
app.include_router(mc_extra_router)

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

@app.get("/monitor")
async def monitor_page():
    return FileResponse(str(BASE_DIR / "Visualized" / "templates" / "monitor.html"))

@app.get("/warning")
async def warning_page():
    return FileResponse(str(BASE_DIR / "Visualized" / "templates" / "warning.html"))

@app.get("/volume_rank")
async def volume_rank_page():
    return FileResponse(str(BASE_DIR / "Visualized" / "templates" / "volume_rank.html"))

if __name__ == "__main__":
    import uvicorn
    # Use port 8080 to match MediaCrawler's default configuration
    uvicorn.run(app, host="127.0.0.1", port=8080)
