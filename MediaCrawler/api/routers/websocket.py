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
from typing import Set, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services import crawler_manager

router = APIRouter(prefix="/crawler", tags=["websocket"])


class ConnectionManager:
    """WebSocket connection manager"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.user_connections: dict[WebSocket, Optional[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: Optional[str] = None):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.user_connections[websocket] = user_id

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        self.user_connections.pop(websocket, None)

    async def broadcast_filtered(self, message: dict, user_id: Optional[str] = None):
        """Broadcast message to connections matching the user_id"""
        if not self.active_connections:
            return

        disconnected = []
        for connection in list(self.active_connections):
            # Only send if user_id matches or if message has no user_id (global log)
            conn_user_id = self.user_connections.get(connection)
            if user_id is None or conn_user_id == user_id:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)

        # Clean up disconnected connections
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast(self, message: dict):
        """Broadcast message to all connections (legacy)"""
        await self.broadcast_filtered(message, None)


manager = ConnectionManager()


async def log_broadcaster():
    """Background task: read logs from queue and broadcast"""
    queue = crawler_manager.get_log_queue()
    while True:
        try:
            # Get log entry from queue
            entry = await queue.get()
            # Broadcast to all WebSocket connections
            # Filter by user_id if provided
            await manager.broadcast_filtered(entry.model_dump(), entry.user_id)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Log broadcaster error: {e}")
            await asyncio.sleep(0.1)


# Global broadcast task
_broadcaster_task: Optional[asyncio.Task] = None


def start_broadcaster():
    """Start broadcast task"""
    global _broadcaster_task
    if _broadcaster_task is None or _broadcaster_task.done():
        _broadcaster_task = asyncio.create_task(log_broadcaster())


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, visualized_user_id: Optional[str] = None):
    """WebSocket log stream"""
    print(f"[WS] New connection attempt for user: {visualized_user_id}")
    uid = str(visualized_user_id) if visualized_user_id else "default"

    try:
        # Ensure broadcast task is running
        start_broadcaster()

        # Accept connection and track by uid (consistent with crawler_manager's internal uid)
        await manager.connect(websocket, uid)
        print(f"[WS] Connected, user: {visualized_user_id}, active connections: {len(manager.active_connections)}")

        # Send existing logs for this user
        user_logs = crawler_manager.get_user_logs(uid)
        for log in user_logs:
            try:
                await websocket.send_json(log.model_dump())
            except Exception as e:
                print(f"[WS] Error sending existing log: {e}")
                break

        print(f"[WS] Sent {len(user_logs)} existing logs, entering main loop")

        while True:
            # Keep connection alive, receive heartbeat or any message
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_text("ping")
                except Exception as e:
                    print(f"[WS] Error sending ping: {e}")
                    break

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {type(e).__name__}: {e}")
    finally:
        manager.disconnect(websocket)
        print(f"[WS] Cleanup done, active connections: {len(manager.active_connections)}")


@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket, visualized_user_id: Optional[str] = None):
    """WebSocket status stream"""
    await websocket.accept()

    try:
        while True:
            # Send status every second for this user
            status = crawler_manager.get_status(visualized_user_id)
            await websocket.send_json(status)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
