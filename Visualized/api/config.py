from fastapi import APIRouter, HTTPException
from .database import query_db, HOTSEARCH_DB_PATH
import sqlite3

# 数据源 1 (uapis.cn) 的平台映射
# 格式: "系统统一ID": "uapis对应的type"
SOURCE1_PLATFORMS = {
    "weibo": "weibo",
    "zhihu": "zhihu",
    "bilibili": "bilibili",
    "acfun": "acfun",
    "douyin": "douyin",
    "kuaishou": "kuaishou",
    "douban-movie": "douban-movie",
    "tieba": "tieba",
    "hupu": "hupu",
    "ngabbs": "ngabbs",
    "v2ex": "v2ex",
    "baidu": "baidu",
    "thepaper": "thepaper",
    "toutiao": "toutiao",
    "qq-news": "qq-news",
    "netease-news": "netease-news",
    "huxiu": "huxiu",
    "sspai": "sspai",
    "juejin": "juejin",
    "jianshu": "jianshu",
    "guokr": "guokr",
    "36kr": "36kr",
    "csdn": "csdn",
    "hellogithub": "hellogithub",
    "lol": "lol",
    "genshin": "genshin",
    "honkai": "honkai",
    "starrail": "starrail",
    "netease-music": "netease-music",
    "qq-music": "qq-music",
    "weread": "weread",
    "earthquake": "earthquake",
    "history": "history",
}

# 数据源 2 (newsnow.busiyi.world) 的平台映射
# 格式: "系统统一ID": "newsnow对应的id"
SOURCE2_PLATFORMS = {
    "v2ex": "v2ex-share",
    "zhihu": "zhihu",
    "weibo": "weibo",
    "douyin": "douyin",
    "hupu": "hupu",
    "tieba": "tieba",
    "toutiao": "toutiao",
    "thepaper": "thepaper",
    "kuaishou": "kuaishou",
    "baidu": "baidu",
    "sspai": "sspai",
    "juejin": "juejin",
    "ifeng": "ifeng",
    "douban-movie": "douban",
    "steam": "steam",
    "qqvideo-tv-hotsearch": "qqvideo-tv-hotsearch",
    "iqiyi-hot-ranklist": "iqiyi-hot-ranklist",
}

# 平台展示名称 (默认展示)
PLATFORM_NAMES = [
    {"id": "weibo", "name": "微博"},
    {"id": "zhihu", "name": "知乎"},
    {"id": "bilibili", "name": "B站"},
    {"id": "douyin", "name": "抖音"},
    {"id": "baidu", "name": "百度"},
    {"id": "hupu", "name": "虎扑"},
    {"id": "toutiao", "name": "今日头条"},
    {"id": "thepaper", "name": "澎湃"},
]

# 所有可用平台 (用于“更多”选择)
ALL_PLATFORMS = [
    {"id": "weibo", "name": "微博"},
    {"id": "zhihu", "name": "知乎"},
    {"id": "bilibili", "name": "B站"},
    {"id": "acfun", "name": "A站"},
    {"id": "douyin", "name": "抖音"},
    {"id": "kuaishou", "name": "快手"},
    {"id": "douban-movie", "name": "豆瓣电影"},
    {"id": "tieba", "name": "百度贴吧"},
    {"id": "hupu", "name": "虎扑"},
    {"id": "ngabbs", "name": "NGA论坛"},
    {"id": "v2ex", "name": "V2EX"},
    {"id": "baidu", "name": "百度"},
    {"id": "thepaper", "name": "澎湃"},
    {"id": "toutiao", "name": "今日头条"},
    {"id": "qq-news", "name": "腾讯新闻"},
    {"id": "netease-news", "name": "网易新闻"},
    {"id": "huxiu", "name": "虎嗅网"},
    {"id": "sspai", "name": "少数派"},
    {"id": "juejin", "name": "掘金"},
    {"id": "jianshu", "name": "简书"},
    {"id": "guokr", "name": "果壳"},
    {"id": "36kr", "name": "36氪"},
    {"id": "csdn", "name": "CSDN"},
    {"id": "hellogithub", "name": "HelloGitHub"},
    {"id": "lol", "name": "英雄联盟"},
    {"id": "genshin", "name": "原神"},
    {"id": "honkai", "name": "崩坏3"},
    {"id": "starrail", "name": "星穹铁道"},
    {"id": "netease-music", "name": "网易云音乐"},
    {"id": "qq-music", "name": "QQ音乐"},
    {"id": "weread", "name": "微信读书"},
    {"id": "earthquake", "name": "地震速报"},
    {"id": "history", "name": "历史上的今天"},
    {"id": "ifeng", "name": "凤凰网"},
    {"id": "steam", "name": "Steam"},
    {"id": "iqiyi-hot-ranklist", "name": "爱奇艺"},
    {"id": "qqvideo-tv-hotsearch", "name": "腾讯视频"},
]

# 热搜 API 数据源配置
HOTSEARCH_SOURCES = {
    "source1": "https://uapis.cn/api/v1/misc/hotboard?type={platform}&t={timestamp}",
    "source2": "https://newsnow.busiyi.world/api/s?id={platform}&latest&t={timestamp}"
}

router = APIRouter(prefix="/config", tags=["config"])

@router.get("/sources")
async def get_config_sources():
    """获取监测源配置"""
    # 模拟数据
    return [
        {"id": 1, "name": "微博热搜爬虫", "type": "weibo", "status": "active", "last_sync": "2026-02-12 10:00:00"},
        {"id": 2, "name": "知乎热榜爬虫", "type": "zhihu", "status": "active", "last_sync": "2026-02-12 09:30:00"},
    ]

@router.get("/keywords")
async def get_keywords():
    """获取监控关键词"""
    rows = query_db("SELECT tag FROM keywords ORDER BY created_at DESC")
    return [row['tag'] for row in rows] if rows else []

@router.post("/keywords")
async def add_keyword(tag: str):
    """添加监控关键词"""
    try:
        conn = sqlite3.connect(HOTSEARCH_DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO keywords (tag) VALUES (?)", (tag,))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Keyword already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/keywords/{tag}")
async def delete_keyword(tag: str):
    """删除监控关键词"""
    try:
        conn = sqlite3.connect(HOTSEARCH_DB_PATH)
        cur = conn.cursor()
        cur.execute("DELETE FROM keywords WHERE tag = ?", (tag,))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
