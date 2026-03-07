import asyncio
import json
import os
import time
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

# Import MediaCrawler components
try:
    from MediaCrawler.api.services import crawler_manager
    from MediaCrawler.api.schemas import CrawlerStartRequest
except ImportError:
    # Fallback for development/testing if MediaCrawler is not in path
    crawler_manager = None
    class CrawlerStartRequest(BaseModel):
        platform: str
        login_type: str
        crawler_type: str
        keywords: Optional[str] = None
        specified_ids: Optional[str] = None

from api.auth import get_current_user, User

# --- Models ---

class ScheduleConfig(BaseModel):
    enabled: bool = True
    mode: str = "interval"  # "interval" or "cron" (cron not fully implemented yet, stick to interval/specific time)
    # For interval mode
    interval_minutes: Optional[int] = 60
    # For specific time mode (daily)
    target_time: Optional[str] = "00:00"  # HH:MM

class ScheduledTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    owner: str  # user ID (as string)
    created_at: int = Field(default_factory=lambda: int(time.time()))
    schedule: ScheduleConfig
    crawler_config: Dict[str, Any]  # Stores the CrawlerStartRequest data
    last_run: int = 0
    next_run: int = 0
    status: str = "pending"  # pending, running, failed, success

class TaskCreateRequest(BaseModel):
    name: str
    owner: str
    schedule: ScheduleConfig
    crawler_config: Dict[str, Any]

# --- Manager ---

class SchedulerManager:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_file = self.data_dir / "scheduler_tasks.json"
        self.tasks: List[ScheduledTask] = []
        self._lock = asyncio.Lock()
        self._running = False
        self._task_loop: Optional[asyncio.Task] = None
        
        # Ensure data directory exists
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
        self.load_tasks()

    def load_tasks(self):
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.tasks = [ScheduledTask(**item) for item in data]
            except Exception as e:
                print(f"Error loading tasks: {e}")
                self.tasks = []

    def save_tasks(self):
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump([task.model_dump() for task in self.tasks], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving tasks: {e}")

    async def add_task(self, task_data: TaskCreateRequest) -> ScheduledTask:
        async with self._lock:
            # Calculate initial next_run
            task = ScheduledTask(
                name=task_data.name,
                owner=task_data.owner,
                schedule=task_data.schedule,
                crawler_config=task_data.crawler_config
            )
            self._update_next_run(task)
            self.tasks.append(task)
            self.save_tasks()
            return task

    async def remove_task(self, task_id: str, owner: str) -> bool:
        async with self._lock:
            original_len = len(self.tasks)
            self.tasks = [t for t in self.tasks if not (t.id == task_id and t.owner == owner)]
            if len(self.tasks) < original_len:
                self.save_tasks()
                return True
            return False

    async def toggle_task(self, task_id: str, owner: str, enabled: bool) -> bool:
        print(f"[{datetime.now()}] Toggling task: id={task_id}, owner={owner}, enabled={enabled}")
        async with self._lock:
            for task in self.tasks:
                if task.id == task_id and task.owner == owner:
                    task.schedule.enabled = enabled
                    if enabled:
                        # Re-calculate next_run when enabled
                        self._update_next_run(task)
                    self.save_tasks()
                    print(f"[{datetime.now()}] Task {task_id} toggled successfully")
                    return True
            print(f"[{datetime.now()}] Task {task_id} NOT found for owner {owner}")
            return False

    async def get_user_tasks(self, owner: str) -> List[ScheduledTask]:
        return [t for t in self.tasks if t.owner == owner]

    def _update_next_run(self, task: ScheduledTask):
        # Use local time for all calculations
        dt_now = datetime.now()
        now_ts = int(dt_now.timestamp())
        
        if task.schedule.mode == "interval":
            interval_seconds = (task.schedule.interval_minutes or 60) * 60
            # For new tasks, set next_run to now + interval
            if task.last_run == 0:
                task.next_run = now_ts + interval_seconds
            else:
                task.next_run = task.last_run + interval_seconds
                # If next run is in past, set to now + 10s to catch up
                if task.next_run < now_ts:
                    task.next_run = now_ts + 10
        
        elif task.schedule.mode == "daily":
            # Parse target time HH:MM
            try:
                target = task.schedule.target_time or "00:00"
                h, m = map(int, target.split(":"))
                
                # Create target datetime for today
                dt_next = dt_now.replace(hour=h, minute=m, second=0, microsecond=0)
                
                # If today's target time has passed, schedule for tomorrow
                if dt_next <= dt_now:
                    dt_next = dt_next + timedelta(days=1)
                
                task.next_run = int(dt_next.timestamp())
            except Exception as e:
                print(f"Error calculating next run for daily task {task.id}: {e}")
                task.next_run = now_ts + 3600 # Fallback 1 hour

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task_loop = asyncio.create_task(self._loop())
        print("Scheduler started")

    async def stop(self):
        self._running = False
        if self._task_loop:
            self._task_loop.cancel()
            try:
                await self._task_loop
            except asyncio.CancelledError:
                pass
        print("Scheduler stopped")

    async def _loop(self):
        while self._running:
            try:
                await self._check_and_run_tasks()
            except Exception as e:
                print(f"Scheduler loop error: {e}")
            await asyncio.sleep(10) # Check every 10 seconds

    async def _check_and_run_tasks(self):
        if not crawler_manager:
            print("Crawler manager not available, skipping tasks")
            return

        now_ts = int(time.time())
        
        # Find tasks due
        tasks_to_run = []
        async with self._lock:
            for task in self.tasks:
                if not task.schedule.enabled:
                    continue
                
                if task.next_run <= now_ts:
                    # Check if this owner's crawler is busy
                    state = crawler_manager._get_user_state(task.owner)
                    if state["process"] and state["process"].returncode is None:
                        # This user is already running a crawler, skip this task for now
                        continue
                        
                    tasks_to_run.append(task)
                    # For simplicity, we can still run one task per loop iteration, 
                    # but now it's per-user isolated
                    # Break here to only run one task in this check cycle, or keep going to run multiple users' tasks
                    # Let's try running multiple if they are different owners
        
        for task_to_run in tasks_to_run:
            print(f"Executing scheduled task: {task_to_run.name} ({task_to_run.id}) for owner: {task_to_run.owner}")
            try:
                # Convert dict to request model
                req_data = task_to_run.crawler_config.copy()
                # Ensure visualized_user_id is set to task owner
                req_data["visualized_user_id"] = task_to_run.owner
                
                # Ensure it matches schema
                start_req = CrawlerStartRequest(**req_data)
                
                success = await crawler_manager.start(start_req)
                
                async with self._lock:
                    task_to_run.last_run = int(time.time())
                    if success:
                        task_to_run.status = "success"
                    else:
                        task_to_run.status = "failed"
                    self._update_next_run(task_to_run)
                    self.save_tasks()
            except Exception as e:
                print(f"Failed to execute task {task_to_run.id}: {e}")
                async with self._lock:
                    task_to_run.status = f"error: {str(e)}"
                    task_to_run.last_run = int(time.time())
                    self._update_next_run(task_to_run)
                    self.save_tasks()

# --- Router ---

router = APIRouter(prefix="/scheduler", tags=["scheduler"])
scheduler = SchedulerManager(data_dir=str(Path(__file__).parent / "data"))

@router.on_event("startup")
async def startup_event():
    await scheduler.start()

@router.on_event("shutdown")
async def shutdown_event():
    await scheduler.stop()

@router.get("/tasks")
async def list_tasks(current_user: User = Depends(get_current_user)):
    """获取当前用户的任务"""
    return await scheduler.get_user_tasks(str(current_user.id))

@router.post("/tasks")
async def create_task(task: TaskCreateRequest, current_user: User = Depends(get_current_user)):
    """创建任务 (强制 owner 为当前用户)"""
    # 强制将 owner 设置为当前登录用户 ID，防止伪造
    task.owner = str(current_user.id)
    return await scheduler.add_task(task)

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, current_user: User = Depends(get_current_user)):
    """删除任务"""
    success = await scheduler.remove_task(task_id, str(current_user.id))
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在或无权删除")
    return {"status": "ok"}

@router.patch("/tasks/{task_id}/toggle")
async def toggle_task(task_id: str, enabled: bool, current_user: User = Depends(get_current_user)):
    """启用/禁用任务"""
    success = await scheduler.toggle_task(task_id, str(current_user.id), enabled)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在或无权操作")
    return {"status": "ok", "enabled": enabled}
