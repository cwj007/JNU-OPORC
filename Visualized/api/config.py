from fastapi import APIRouter

# 平台 ID 映射配置
PLATFORM_MAPPING = {
    "bilibili-hot-search": "bilibili",
    "baidu": "baidu",
    "toutiao": "toutiao",
    "zhihu": "zhihu",
    "weibo": "weibo",
    "douyin": "douyin",
    "thepaper": "thepaper",
    "hupu": "hupu"
}

# 平台展示名称
PLATFORM_NAMES = [
    {"id": "weibo", "name": "微博"},
    {"id": "baidu", "name": "百度热搜"},
    {"id": "toutiao", "name": "今日头条"},
    {"id": "zhihu", "name": "知乎"},
    {"id": "douyin", "name": "抖音"},
    {"id": "bilibili-hot-search", "name": "B站热搜"},
    {"id": "thepaper", "name": "澎湃新闻"},
    {"id": "hupu", "name": "虎扑"}
]

router = APIRouter(prefix="/config", tags=["config"])

@router.get("/sources")
async def get_config_sources():
    """获取监测源配置"""
    return [
        {"id": 1, "name": "微博监测", "type": "weibo", "status": "active", "last_sync": "2026-02-10 11:00:00"},
        {"id": 2, "name": "小红书监测", "type": "xhs", "status": "inactive", "last_sync": "N/A"},
    ]
