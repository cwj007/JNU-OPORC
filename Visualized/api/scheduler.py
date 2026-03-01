
import asyncio
import json
import time
import os
import sys
import anyio
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
from .auth import get_current_admin

# Project Root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEDULER_CONFIG_PATH = Path(__file__).parent / "scheduler_config.json"
LOG_DIR = PROJECT_ROOT / "Visualized" / "logs"

if not LOG_DIR.exists():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/scheduler", tags=["scheduler"], dependencies=[Depends(get_current_admin)])

class SchedulerConfig(BaseModel):
    enabled: bool = False
    mode: str = "time"  # "time" (specific time) or "interval" (every X minutes)
    target_time: str = "00:00"  # HH:MM format
    interval_minutes: int = 60
    last_run: float = 0
    script_path: str = "Workflow: get_specified_ids -> main.py"

# Global state
current_config = SchedulerConfig()
scheduler_task = None

def load_config():
    global current_config
    if SCHEDULER_CONFIG_PATH.exists():
        try:
            with open(SCHEDULER_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                current_config = SchedulerConfig(**data)
        except Exception as e:
            print(f"Error loading scheduler config: {e}")

def save_config():
    try:
        with open(SCHEDULER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current_config.dict(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving scheduler config: {e}")

async def run_crawler_script():
    """Run the crawler script workflow in subprocesses"""
    print(f"[{datetime.now()}] Scheduler triggering task workflow")
    
    # Log file
    log_file = LOG_DIR / f"scheduler_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    media_crawler_dir = PROJECT_ROOT / "MediaCrawler"
    env = os.environ.copy()
    # 强制子进程使用 UTF-8 编码，防止 Windows 下输出乱码
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    
    try:
        f = open(log_file, "w", encoding="utf-8")
        try:
            # Step 1: Get Specified IDs
            f.write(f"[{datetime.now()}] === Step 1: Getting Specified IDs ===\n")
            f.flush()
            
            cmd1 = ["uv", "run", "--frozen", "python", "-m", "media_platform.weibo.get_specified_ids", "--lt", "cookie"]
            
            process1 = await asyncio.create_subprocess_exec(
                *cmd1,
                stdout=f,
                stderr=f,
                cwd=str(media_crawler_dir),
                env=env
            )
            
            print(f"[{datetime.now()}] Step 1 started with PID: {process1.pid}")
            await process1.wait()
            print(f"[{datetime.now()}] Step 1 finished with return code: {process1.returncode}")
            
            if process1.returncode != 0:
                f.write(f"\n[{datetime.now()}] Step 1 failed with return code {process1.returncode}. Aborting workflow.\n")
                return

            # Ensure file system sync and give a small buffer
            f.write(f"[{datetime.now()}] Step 1 completed successfully. Waiting 3 seconds before starting Step 2...\n")
            f.flush()
            await asyncio.sleep(3)

            f.write(f"\n[{datetime.now()}] === Step 2: Crawling Details ===\n")
            f.flush()

            # Step 2: Crawl Details
            # Command: uv run --frozen main.py --platform wb --type detail --lt cookie --save_data_option sqlite
            cmd2 = ["uv", "run", "--frozen", "main.py", "--platform", "wb", "--type", "detail", "--lt", "cookie", "--save_data_option", "sqlite"]
            
            process2 = await asyncio.create_subprocess_exec(
                *cmd2,
                stdout=f,
                stderr=f,
                cwd=str(media_crawler_dir),
                env=env
            )
            
            print(f"[{datetime.now()}] Step 2 started with PID: {process2.pid}")
            await process2.wait()
            print(f"[{datetime.now()}] Step 2 finished with return code: {process2.returncode}")
            
            f.write(f"\n[{datetime.now()}] Workflow finished with return code: {process2.returncode}\n")

        finally:
            f.close()
                
    except Exception as e:
        print(f"Error running scheduler task: {e}")

async def scheduler_loop():
    """Main scheduler loop"""
    print("Scheduler loop started.")
    while True:
        try:
            if current_config.enabled:
                now = datetime.now()
                should_run = False
                
                if current_config.mode == "time":
                    # Check if current time matches target_time
                    current_hm = now.strftime("%H:%M")
                    if current_hm == current_config.target_time:
                        # Avoid running multiple times in the same minute
                        # Check if we already ran today
                        last_run_dt = datetime.fromtimestamp(current_config.last_run)
                        if last_run_dt.date() != now.date() or (now.timestamp() - current_config.last_run > 60):
                            should_run = True
                
                elif current_config.mode == "interval":
                    # Check interval
                    if (now.timestamp() - current_config.last_run) >= (current_config.interval_minutes * 60):
                        should_run = True
                
                if should_run:
                    current_config.last_run = now.timestamp()
                    save_config() # Save last_run
                    # Run task
                    asyncio.create_task(run_crawler_script())
            
            # Check every 30 seconds
            await asyncio.sleep(30)
            
        except Exception as e:
            print(f"Error in scheduler loop: {e}")
            await asyncio.sleep(60)

@router.get("/config")
async def get_config():
    return current_config

@router.post("/config")
async def update_config(config: SchedulerConfig):
    global current_config
    current_config = config
    save_config()
    return current_config

@router.get("/logs")
async def get_logs(limit: int = 50):
    """Get logs from the latest run"""
    try:
        log_files = sorted(LOG_DIR.glob("scheduler_run_*.log"), key=os.path.getmtime, reverse=True)
        if not log_files:
            return {"logs": ["No logs found."]}
        
        latest_log = log_files[0]
        logs = []
        # 使用 anyio 异步读取文件，防止大日志阻塞
        async def read_file():
            with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
                return f.readlines()
        
        logs = await anyio.to_thread.run_sync(read_file)
            
        return {"logs": [line.strip() for line in logs[-limit:]]}
    except Exception as e:
        return {"logs": [f"Error reading logs: {str(e)}"]}

@router.post("/start")
async def start_task_manually(background_tasks: BackgroundTasks):
    """Manually trigger the task"""
    background_tasks.add_task(run_crawler_script)
    return {"status": "Task started in background"}

# Initialize
load_config()

def start_scheduler():
    global scheduler_task
    if scheduler_task is None:
        scheduler_task = asyncio.create_task(scheduler_loop())
