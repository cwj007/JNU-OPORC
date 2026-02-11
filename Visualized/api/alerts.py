from fastapi import APIRouter

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("/list")
async def get_alerts():
    """获取预警列表"""
    # 模拟数据
    return [
        {"id": 1, "level": "high", "title": "发现疑似负面舆情爆发", "time": "2026-02-10 10:00:00", "status": "unread"},
        {"id": 2, "level": "medium", "title": "关键词“千问”热度激增", "time": "2026-02-10 09:30:00", "status": "read"},
    ]
