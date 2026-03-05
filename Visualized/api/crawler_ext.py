# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, List
from .auth import get_current_user, User
from MediaCrawler.tools.cookie_cache import get_cookie_cache, get_all_cookie_cache

router = APIRouter(prefix="/crawler-ext", tags=["crawler-ext"])

@router.get("/my-cookies")
async def get_my_cookies(platform: str = None, current_user: User = Depends(get_current_user)):
    """获取当前登录用户的 Cookie 缓存"""
    # 如果是管理员，可以查看所有（或者传入特定的 visualized_user_id）
    # 如果是普通用户，只返回属于自己的 Cookie
    visualized_user_id = str(current_user.id)
    
    # 如果是管理员，我们允许通过查询参数覆盖 visualized_user_id 来查看别人的（可选）
    # if current_user.role == 'admin' and target_user_id:
    #     visualized_user_id = target_user_id

    if platform:
        return {"cookies": get_cookie_cache(platform, visualized_user_id)}
    return {"cookies": get_all_cookie_cache(visualized_user_id)}

@router.get("/all-cookies")
async def get_all_cookies(platform: str = None, current_user: User = Depends(get_current_user)):
    """获取所有用户的 Cookie 缓存 (仅限管理员)"""
    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="仅限管理员访问")
    
    if platform:
        return {"cookies": get_cookie_cache(platform)}
    return {"cookies": get_all_cookie_cache()}
