
import sys
import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image
from io import BytesIO

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

# Try to import config, fallback to hardcoded path
try:
    from Transformers.config import MEDIA_CRAWLER_DATA_DIR
except ImportError:
    # Fallback path based on known project structure
    MEDIA_CRAWLER_DATA_DIR = Path(r"e:\JNU-OPORC\MediaCrawler\data")

app = FastAPI(title="JNU-OPORC Image Server")

# Allow CORS for main application access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

print(f"Initializing Image Server...")

# 1. Mount MediaCrawler Data (Main images)
if MEDIA_CRAWLER_DATA_DIR.exists():
    print(f"Mounting /media -> {MEDIA_CRAWLER_DATA_DIR}")
    app.mount("/media", StaticFiles(directory=str(MEDIA_CRAWLER_DATA_DIR)), name="media")
else:
    print(f"Warning: Media directory not found: {MEDIA_CRAWLER_DATA_DIR}")

# 2. Mount Logos
LOGOS_DIR = Path(r"e:\JNU-OPORC\Visualized\logos")
if LOGOS_DIR.exists():
    print(f"Mounting /logos -> {LOGOS_DIR}")
    app.mount("/logos", StaticFiles(directory=str(LOGOS_DIR)), name="logos")

# 3. Mount Static (Optional, for completeness)
STATIC_DIR = Path(r"e:\JNU-OPORC\Visualized\static")
if STATIC_DIR.exists():
    print(f"Mounting /static -> {STATIC_DIR}")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "image_server", "port": 8002}

@app.get("/thumbnail/{file_path:path}")
async def get_thumbnail(file_path: str, width: int = 200):
    """
    实时生成缩略图
    path example: media/weibo/xxx.jpg
    """
    try:
        real_path = None
        # 解析真实路径
        if file_path.startswith("media/"):
            # 移除前缀 media/
            rel_path = file_path[6:] 
            real_path = MEDIA_CRAWLER_DATA_DIR / rel_path
        elif file_path.startswith("logos/"):
            rel_path = file_path[6:]
            real_path = LOGOS_DIR / rel_path
            
        if not real_path or not real_path.exists():
            return Response(status_code=404)
            
        # 生成缩略图
        with Image.open(real_path) as img:
            # 转换为 RGB (防止 RGBA 保存为 JPEG 报错)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new(img.mode[:-1], img.size, (255, 255, 255))
                background.paste(img, img.split()[-1])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 计算缩略图尺寸
            aspect_ratio = img.height / img.width
            height = int(width * aspect_ratio)
            
            img.thumbnail((width, height))
            
            # 保存到内存
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=60) # 降低质量以提升速度
            return Response(content=buf.getvalue(), media_type="image/jpeg")
            
    except Exception as e:
        print(f"Error generating thumbnail for {file_path}: {e}")
        return Response(status_code=500)

if __name__ == "__main__":
    print("Starting Independent Image Server on port 8002...")
    print("Please ensure your main application points to http://localhost:8002 for media resources.")
    uvicorn.run(app, host="0.0.0.0", port=8002)
