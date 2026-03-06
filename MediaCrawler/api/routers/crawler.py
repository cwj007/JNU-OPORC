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

from typing import Optional, Any
from fastapi import APIRouter, HTTPException, Depends

from ..schemas import CrawlerStartRequest, CrawlerStatusResponse
from ..services import crawler_manager
from tools.cookie_cache import get_cookie_cache, get_all_cookie_cache, get_latest_cookie_str

# 尝试导入认证模块以支持多用户隔离
try:
    from Visualized.api.auth import get_current_user
    HAS_AUTH = True
except ImportError:
    # 兼容独立运行模式
    async def get_current_user():
        return None
    HAS_AUTH = False

router = APIRouter(prefix="/crawler", tags=["crawler"])


@router.get("/cookie-cache")
async def get_cookies(platform: str = None, visualized_user_id: str = None, current_user: Any = Depends(get_current_user)):
    """Get cached cookies"""
    # 优先使用登录用户的 id
    user_id = str(current_user.id) if current_user else visualized_user_id
    
    if platform:
        return {"cookies": get_cookie_cache(platform, user_id)}
    return {"cookies": get_all_cookie_cache(user_id)}


@router.get("/cookie")
async def get_latest_cookie(platform: str, visualized_user_id: str = None, current_user: Any = Depends(get_current_user)):
    """获取指定平台的最新 Cookie 字符串"""
    user_id = str(current_user.id) if current_user else visualized_user_id
    cookie_str = get_latest_cookie_str(platform, user_id)
    return {"cookie": cookie_str}


@router.post("/start")
async def start_crawler(request: CrawlerStartRequest, current_user: Any = Depends(get_current_user)):
    """Start crawler task"""
    # 注入当前用户 id 到请求中
    if current_user:
        request.visualized_user_id = str(current_user.id)
    
    user_id = request.visualized_user_id
    
    success = await crawler_manager.start(request)
    if not success:
        # Handle concurrent/duplicate requests: if process is already running, return 400 instead of 500
        state = crawler_manager._get_user_state(user_id)
        if state["process"] and state["process"].returncode is None:
            raise HTTPException(status_code=400, detail="Crawler is already running")
        raise HTTPException(status_code=500, detail="Failed to start crawler")

    return {"status": "ok", "message": "Crawler started successfully"}


@router.post("/stop")
async def stop_crawler(visualized_user_id: Optional[str] = None, current_user: Any = Depends(get_current_user)):
    """Stop crawler task"""
    user_id = str(current_user.id) if current_user else visualized_user_id
    
    success = await crawler_manager.stop(user_id)
    if not success:
        # Handle concurrent/duplicate requests: if process already exited/doesn't exist, return 400 instead of 500
        state = crawler_manager._get_user_state(user_id)
        if not state["process"] or state["process"].returncode is not None:
            raise HTTPException(status_code=400, detail="No crawler is running")
        raise HTTPException(status_code=500, detail="Failed to stop crawler")

    return {"status": "ok", "message": "Crawler stopped successfully"}


@router.get("/status", response_model=CrawlerStatusResponse)
async def get_crawler_status(visualized_user_id: Optional[str] = None, current_user: Any = Depends(get_current_user)):
    """Get crawler status"""
    user_id = str(current_user.id) if current_user else visualized_user_id
    return crawler_manager.get_status(user_id)


@router.get("/logs")
async def get_logs(limit: int = 100, visualized_user_id: Optional[str] = None, current_user: Any = Depends(get_current_user)):
    """Get recent logs"""
    user_id = str(current_user.id) if current_user else visualized_user_id
    
    if user_id:
        logs = crawler_manager.get_user_logs(user_id)
        logs = logs[-limit:] if limit > 0 else logs
    else:
        # Fallback to global logs if no user_id provided (e.g. older clients)
        logs = crawler_manager.logs[-limit:] if limit > 0 else crawler_manager.logs
    return {"logs": [log.model_dump() for log in logs]}
