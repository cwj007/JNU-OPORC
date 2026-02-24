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
    owner: str  # username
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
        
        # Check if crawler is busy
        # Note: crawler_manager.process is subprocess.Popen
        is_busy = False
        if crawler_manager.process and crawler_manager.process.poll() is None:
            is_busy = True
            
        if is_busy:
            # Can't run anything now
            return

        # Find tasks due
        task_to_run = None
        async with self._lock:
            for task in self.tasks:
                if not task.schedule.enabled:
                    continue
                
                if task.next_run <= now_ts:
                    task_to_run = task
                    break # Run one at a time
        
        if task_to_run:
            print(f"Executing scheduled task: {task_to_run.name} ({task_to_run.id})")
            try:
                # Convert dict to request model
                req_data = task_to_run.crawler_config.copy()
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
async def list_tasks(username: str):
    # In a real app, username should come from auth token
    return await scheduler.get_user_tasks(username)

@router.post("/tasks")
async def create_task(task: TaskCreateRequest):
    return await scheduler.add_task(task)

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, username: str):
    success = await scheduler.remove_task(task_id, username)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or permission denied")
    return {"status": "ok"}
