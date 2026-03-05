# JNU-OPORC API 接口文档

本文档详细说明了 JNU-OPORC 舆情监测系统的后端 API 接口、请求参数及返回结构。

## 1. 通用说明

### 1.1 基础地址 (Base URL)
- 系统默认运行地址：`http://localhost:8000` (Visualized 综合服务)
- MediaCrawler 独立服务：`http://localhost:8080` (可选，通常通过 8000 转发)
- 图片资源服务器：`http://localhost:8002` (专门处理多媒体文件与缩略图)

### 1.2 认证方式 (Authentication)
大部分 API 需要在 HTTP Header 中携带 Bearer Token 进行认证。
- **Header 名称**: `Authorization`
- **格式**: `Bearer <your_token>`

---

## 2. 身份认证 (Auth)

### 2.1 用户登录
- **接口**: `POST /api/auth/login`
- **功能**: 获取访问令牌
- **请求体 (JSON)**:
  ```json
  {
    "username": "admin",
    "password": "your_password"
  }
  ```
- **成功响应 (200 OK)**:
  ```json
  {
    "token": "a1b2c3d4e5f6...",
    "username": "admin",
    "role": "admin"
  }
  ```

### 2.2 用户退出
- **接口**: `POST /api/auth/logout`
- **Header**: `Authorization: Bearer <token>`
- **成功响应 (200 OK)**:
  ```json
  {
    "message": "Logged out"
  }
  ```

---

## 3. 热搜监测 (Hotsearch)

### 3.1 获取所有平台热搜汇总
- **接口**: `GET /api/hotsearch/all`
- **参数**:
  - `refresh` (bool): 是否强制实时抓取，默认 false
  - `all_platforms` (bool): 是否返回所有支持的平台，默认 false
- **成功响应 (200 OK)**:
  ```json
  [
    {
      "id": "weibo",
      "name": "微博热搜",
      "status": "cached",
      "fetch_time": "2024-03-20 14:30:00",
      "data": [
        {
          "title": "热搜话题名称",
          "url": "https://s.weibo.com/...",
          "hot": "1234567",
          "rank": 1,
          "trend": 1, 
          "previous_rank": 3,
          "is_new": false
        }
      ]
    }
  ]
  ```
  - `trend` 说明: `1` 上升, `-1` 下降, `0` 持平。

### 3.2 获取平台列表
- **接口**: `GET /api/hotsearch/platforms`
- **成功响应 (200 OK)**:
  ```json
  {
    "platforms": [
      {"id": "weibo", "name": "微博"},
      {"id": "zhihu", "name": "知乎"}
    ]
  }
  ```

---

## 4. 舆情监测 (Monitoring)

### 4.1 获取舆情列表 (分页筛选)
- **接口**: `GET /api/monitoring/list`
- **Header**: `Authorization: Bearer <token>`
- **参数**:
  - `page` (int): 页码，默认 1
  - `size` (int): 每页条数，默认 20
  - `sentiment` (str): 情感筛选 (positive, negative, neutral)
  - `keyword` (str): 关键词搜索
  - `platforms` (str): 平台筛选，如 "weibo,xhs"
- **成功响应 (200 OK)**:
  ```json
  {
    "total": 150,
    "page": 1,
    "size": 20,
    "items": [
      {
        "id": 1,
        "note_id": "note_123",
        "title": "帖子标题",
        "desc": "帖子内容描述",
        "user_nickname": "作者昵称",
        "sentiment": "negative",
        "source": "weibo",
        "created_at": "2024-03-20 10:00:00",
        "sentiment_analysis": {
          "reasoning": "分析理由...",
          "irony_detected": false
        }
      }
    ]
  }
  ```

### 4.2 更新分析结果 (标注)
- **接口**: `POST /api/monitoring/update_training_result`
- **请求体 (JSON)**:
  ```json
  {
    "note_id": "note_123",
    "sentiment": "negative",
    "reasoning": "由于包含大量负面词汇...",
    "original_data": { ... }
  }
  ```

---

## 5. 实时预警 (Alerts)

### 5.1 获取预警列表
- **接口**: `GET /api/alerts/list`
- **参数**:
  - `days` (int): 查询过去几天的数据，默认 1
  - `level` (str): 级别筛选 (high, medium, low)
- **成功响应 (200 OK)**:
  ```json
  {
    "total": 5,
    "items": [
      {
        "id": 10,
        "type": "keyword_match",
        "level": "high",
        "title": "发现高危舆情",
        "content": "匹配到关键词: 罢工",
        "time": "2024-03-20 12:00:00",
        "meta_data": {
          "note_id": "xxx",
          "platform": "weibo"
        }
      }
    ]
  }
  ```

---

## 6. 爬虫控制 (MediaCrawler)

### 6.1 启动爬虫任务
- **接口**: `POST /api/crawler/start`
- **请求体 (JSON)**:
  ```json
  {
    "platform": "xhs",
    "login_type": "qrcode",
    "crawler_type": "search",
    "keywords": "关键词1,关键词2",
    "crawler_max_notes_count": 20,
    "save_option": "sqlite"
  }
  ```
- **成功响应 (200 OK)**:
  ```json
  {
    "status": "ok",
    "message": "Crawler started successfully"
  }
  ```

### 6.2 获取爬虫状态
- **接口**: `GET /api/crawler/status`
- **成功响应 (200 OK)**:
  ```json
  {
    "status": "running",
    "platform": "xhs",
    "crawler_type": "search",
    "started_at": "2024-03-20T14:00:00"
  }
  ```

### 6.3 实时日志 (WebSocket)
- **接口**: `WS /api/ws/logs`
- **数据结构 (JSON)**:
  ```json
  {
    "time": "14:30:05",
    "level": "INFO",
    "message": "正在抓取第 5 条数据...",
    "platform": "xhs"
  }
  ```

---

## 7. 任务调度 (Workflow)

### 7.1 获取调度配置
- **接口**: `GET /api/workflow/config`
- **Header**: `Authorization: Bearer <admin_token>`
- **成功响应 (200 OK)**:
  ```json
  {
    "enabled": true,
    "mode": "interval",
    "interval_minutes": 60,
    "target_time": "00:00",
    "last_run": 1710921600.0,
    "script_path": "Workflow: get_specified_ids -> main.py"
  }
  ```

---

## 8. 图片资源服务 (Image Server - Port 8002)

专门用于处理、压缩与提供采集到的多媒体资源（图片、视频）。

### 8.1 静态资源访问
- **基础路径**: `GET http://localhost:8002/media/{rel_path}`
- **说明**: 直接映射 `MediaCrawler/data` 目录，用于访问原始图片。
- **示例**: `http://localhost:8002/media/weibo/pic_123.jpg`

### 8.2 缩略图实时生成
- **接口**: `GET /thumbnail/{file_path:path}`
- **参数**:
  - `width` (int): 缩略图宽度，默认 200，高度按比例缩放。
- **功能**: 自动加载指定路径的图片，调整尺寸并转换为 Web 优化的 JPEG 格式。
- **示例**: `http://localhost:8002/thumbnail/media/xhs/post_abc.png?width=400`

### 8.3 平台图标访问
- **基础路径**: `GET http://localhost:8002/logos/{platform}.png`
- **说明**: 访问系统内置的各社交平台 Logo 图标。
