# -*- coding: utf-8 -*-
# Copyright (c) 2025 JJ_Superman
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/cwj007/JNU-OPORC/tree/master
# GitHub: https://github.com/cwj007
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import asyncio
import subprocess
import signal
import os
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path

from ..schemas import CrawlerStartRequest, LogEntry


class CrawlerManager:
    """Crawler process manager"""

    def __init__(self):
        self._lock = asyncio.Lock()
        # user_id -> {process, status, started_at, config, read_task}
        self._user_states: Dict[str, dict] = {}
        self._log_id = 0
        self._logs: List[LogEntry] = []  # Keep this for backward compatibility or global logs if needed
        self._user_logs: Dict[str, List[LogEntry]] = {} # user_id -> logs
        # Project root directory
        self._project_root = Path(__file__).parent.parent.parent
        # Log queue - for pushing to WebSocket
        self._log_queue: Optional[asyncio.Queue] = None

    def _get_user_state(self, user_id: Optional[str]) -> dict:
        """Get or initialize user state"""
        uid = str(user_id) if user_id else "default"
        if uid not in self._user_states:
            self._user_states[uid] = {
                "process": None,
                "status": "idle",
                "started_at": None,
                "config": None,
                "read_task": None
            }
        return self._user_states[uid]

    @property
    def process(self) -> Optional[subprocess.Popen]:
        """Default process for backward compatibility"""
        return self._get_user_state(None)["process"]

    @property
    def status(self) -> str:
        """Default status for backward compatibility"""
        return self._get_user_state(None)["status"]

    @property
    def started_at(self) -> Optional[datetime]:
        """Default started_at for backward compatibility"""
        return self._get_user_state(None)["started_at"]

    @property
    def current_config(self) -> Optional[CrawlerStartRequest]:
        """Default current_config for backward compatibility"""
        return self._get_user_state(None)["config"]

    @property
    def logs(self) -> List[LogEntry]:
        """Global logs (deprecated, use get_user_logs)"""
        return self._logs

    def get_user_logs(self, user_id: Optional[str]) -> List[LogEntry]:
        """Get logs for a specific user"""
        uid = str(user_id) if user_id else "default"
        return self._user_logs.get(uid, [])

    def get_log_queue(self) -> asyncio.Queue:
        """Get or create log queue"""
        if self._log_queue is None:
            self._log_queue = asyncio.Queue()
        return self._log_queue

    def _create_log_entry(self, message: str, level: str = "info", user_id: str = None) -> LogEntry:
        """Create log entry"""
        self._log_id += 1
        entry = LogEntry(
            id=self._log_id,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            level=level,
            message=message,
            user_id=user_id
        )
        
        # Add to global logs (deprecated)
        self._logs.append(entry)
        if len(self._logs) > 500:
            self._logs = self._logs[-500:]

        # Add to per-user logs
        if user_id:
            if user_id not in self._user_logs:
                self._user_logs[user_id] = []
            
            user_logs = self._user_logs[user_id]
            user_logs.append(entry)
            # Keep last 500 logs per user
            if len(user_logs) > 500:
                self._user_logs[user_id] = user_logs[-500:]
        
        return entry

    async def _push_log(self, entry: LogEntry):
        """Push log to queue"""
        if self._log_queue is not None:
            try:
                self._log_queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    def _parse_log_level(self, line: str) -> str:
        """Parse log level"""
        line_upper = line.upper()
        if "ERROR" in line_upper or "FAILED" in line_upper:
            return "error"
        elif "WARNING" in line_upper or "WARN" in line_upper:
            return "warning"
        elif "SUCCESS" in line_upper or "完成" in line or "成功" in line:
            return "success"
        elif "DEBUG" in line_upper:
            return "debug"
        return "info"

    async def start(self, config: CrawlerStartRequest) -> bool:
        """Start crawler process"""
        async with self._lock:
            user_id = config.visualized_user_id
            state = self._get_user_state(user_id)
            
            if state["process"] and state["process"].returncode is None:
                return False

            # Clear old logs for this user
            uid = str(user_id) if user_id else "default"
            self._user_logs[uid] = []

            # Ensure log queue exists
            if self._log_queue is None:
                self._log_queue = asyncio.Queue()
            
            # Note: We no longer clear the global log queue here to support multi-user isolation.
            # Each user's logs will be filtered by the WebSocket broadcaster.

            # Build command line arguments
            cmd = self._build_command(config)

            # Log start information
            entry = self._create_log_entry(f"Starting crawler: {' '.join(cmd)}", "info", user_id=uid)
            await self._push_log(entry)

            # Create process with environment variables
            env = os.environ.copy()
            if config.visualized_user_id:
                env["VISUALIZED_USER_ID"] = config.visualized_user_id

            try:
                state["process"] = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(self._project_root),
                    env=env
                )

                state["status"] = "running"
                state["started_at"] = datetime.now()
                state["config"] = config.model_dump()

                entry = self._create_log_entry(
                    f"Crawler started on platform: {config.platform.value}, type: {config.crawler_type.value}",
                    "success",
                    user_id=uid
                )
                await self._push_log(entry)

                # Start log reading task
                state["read_task"] = asyncio.create_task(self._read_output(user_id))

                return True
            except Exception as e:
                state["status"] = "error"
                entry = self._create_log_entry(f"Failed to start crawler: {str(e)}", "error", user_id=uid)
                await self._push_log(entry)
                return False

    async def stop(self, user_id: Optional[str] = None) -> bool:
        """Stop crawler process"""
        async with self._lock:
            state = self._get_user_state(user_id)
            uid = str(user_id) if user_id else "default"
            
            if not state["process"] or state["process"].returncode is not None:
                return False

            state["status"] = "stopping"
            entry = self._create_log_entry("Sending SIGTERM to crawler process...", "warning", user_id=uid)
            await self._push_log(entry)

            try:
                # On Windows, send_signal(signal.SIGTERM) is not supported. 
                # Use terminate() which works on both Windows and Unix.
                state["process"].terminate()

                # Wait for graceful exit (up to 15 seconds)
                for _ in range(30):
                    if state["process"].returncode is not None:
                        break
                    await asyncio.sleep(0.5)

                # If still not exited, force kill
                if state["process"].returncode is None:
                    entry = self._create_log_entry("Process not responding, sending SIGKILL...", "warning", user_id=uid)
                    await self._push_log(entry)
                    state["process"].kill()
                    # Wait for force kill to take effect
                    await asyncio.sleep(0.5)

                entry = self._create_log_entry("Crawler process terminated", "info", user_id=uid)
                await self._push_log(entry)
                
                # 彻底清理资源
                state["status"] = "idle"
                state["config"] = None
                state["process"] = None
                state["started_at"] = None

            except Exception as e:
                entry = self._create_log_entry(f"Error stopping crawler: {str(e)}", "error", user_id=uid)
                await self._push_log(entry)
                state["status"] = "idle"
                state["config"] = None
                state["process"] = None
                state["started_at"] = None

            # Cancel and clear log reading task
            if state["read_task"]:
                state["read_task"].cancel()
                state["read_task"] = None

            return True

    def get_status(self, user_id: Optional[str] = None) -> dict:
        """Get current status"""
        state = self._get_user_state(user_id)
        
        # 兜底检查：如果状态是运行中，检查进程是否真的还在运行
        if state["status"] in ("running", "stopping") and state["process"]:
            # returncode 不为 None 表示进程已结束
            if state["process"].returncode is not None:
                state["status"] = "idle"
                state["config"] = None
        
        config = state["config"]
        
        # Note: config is stored as a dict (via model_dump())
        platform = config.get("platform") if config else None
        crawler_type = config.get("crawler_type") if config else None
        
        return {
            "status": state["status"],
            "platform": platform,
            "crawler_type": crawler_type,
            "started_at": state["started_at"] if state["started_at"] else None,
            "error_message": None
        }

    def _build_command(self, config: CrawlerStartRequest) -> list:
        """Build main.py command line arguments"""
        # Use --frozen to ensure the environment matches the lockfile exactly, consistent with local manual execution
        # According to workspace rules, 'python' is not needed when using uv run --frozen
        cmd = ["uv", "run", "--frozen", "main.py"]

        cmd.extend(["--platform", config.platform.value])
        cmd.extend(["--lt", config.login_type.value])
        cmd.extend(["--type", config.crawler_type.value])
        cmd.extend(["--save_data_option", config.save_option.value])

        # Pass different arguments based on crawler type
        if config.crawler_type.value == "search" and config.keywords:
            cmd.extend(["--keywords", config.keywords])
        elif config.crawler_type.value == "detail" and config.specified_ids:
            cmd.extend(["--specified_id", config.specified_ids])
        elif config.crawler_type.value == "creator" and config.creator_ids:
            cmd.extend(["--creator_id", config.creator_ids])

        if config.start_page != 1:
            cmd.extend(["--start", str(config.start_page)])

        cmd.extend(["--get_comment", "true" if config.enable_comments else "false"])
        cmd.extend(["--get_sub_comment", "true" if config.enable_sub_comments else "false"])

        if config.cookies:
            cmd.extend(["--cookies", config.cookies])

        cmd.extend(["--headless", "true" if config.headless else "false"])

        if config.visualized_user_id:
            cmd.extend(["--visualized_user_id", config.visualized_user_id])

        # New configuration parameters
        if config.enable_ip_proxy:
            cmd.extend(["--enable_ip_proxy", "true"])
            cmd.extend(["--ip_proxy_pool_count", str(config.ip_proxy_pool_count)])
            cmd.extend(["--enable_validate_ip", "true" if config.enable_validate_ip else "false"])
            cmd.extend(["--ip_proxy_provider_name", config.ip_proxy_provider_name])
            cmd.extend(["--wandou_app_key", config.wandou_app_key])
            cmd.extend(["--kdl_secret_id", config.kdl_secret_id])
            cmd.extend(["--kdl_signature", config.kdl_signature])
            cmd.extend(["--kdl_user_name", config.kdl_user_name])
            cmd.extend(["--kdl_user_pwd", config.kdl_user_pwd])
        else:
            cmd.extend(["--enable_ip_proxy", "false"])

        cmd.extend(["--crawler_max_notes_count", str(config.crawler_max_notes_count)])
        cmd.extend(["--max_concurrency_num", str(config.max_concurrency_num)])
        cmd.extend(["--max_comments_count_singlenotes", str(config.crawler_max_comments_count_singlenotes)])
        
        if config.platform.value == "wb" and config.crawler_type.value == "search":
            cmd.extend(["--weibo_search_type", config.weibo_search_type])

        return cmd

    async def _read_output(self, user_id: str = None):
        """Asynchronously read process output"""
        state = self._get_user_state(user_id)
        uid = str(user_id) if user_id else "default"

        try:
            # For asyncio.subprocess.Process, stdout is a StreamReader
            while state["process"]:
                line_bytes = await state["process"].stdout.readline()
                if not line_bytes:
                    break
                
                line = line_bytes.decode("utf-8", errors="ignore").strip()
                if line:
                    level = self._parse_log_level(line)
                    entry = self._create_log_entry(line, level, user_id=uid)
                    await self._push_log(entry)

            # 等待进程完全结束并获取退出码
            if state["process"]:
                try:
                    # 给一点时间让进程自然结束，避免 readline 结束后 returncode 还没更新
                    await asyncio.wait_for(state["process"].wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                
                exit_code = state["process"].returncode
                
                # 只要进程结束了，且当前状态不是 idle，就更新为 idle
                if state["status"] != "idle":
                    if exit_code == 0:
                        entry = self._create_log_entry("Crawler completed successfully", "success", user_id=uid)
                    elif exit_code is not None:
                        entry = self._create_log_entry(f"Crawler exited with code: {exit_code}", "warning", user_id=uid)
                    else:
                        entry = self._create_log_entry("Crawler process finished", "info", user_id=uid)
                    
                    await self._push_log(entry)
                    
                    # 彻底清理资源
                    state["status"] = "idle"
                    state["config"] = None
                    state["process"] = None
                    state["started_at"] = None
                    # 读取任务在完成后会自动销毁，但也可以手动置空以防引用残留
                    state["read_task"] = None

        except asyncio.CancelledError:
            pass
        except Exception as e:
            entry = self._create_log_entry(f"Error reading process output: {str(e)}", "error", user_id=uid)
            await self._push_log(entry)
            # 发生异常也尝试重置状态并清理资源
            if state["status"] != "idle":
                state["status"] = "idle"
                state["config"] = None
                state["process"] = None
                state["started_at"] = None
                state["read_task"] = None


# Global singleton
crawler_manager = CrawlerManager()
