# JNU-OPORC 系统目录架构与操作手册

本仓库是一个综合性的舆情监测与分析系统，由数据采集、智能分析和可视化管理三大核心模块组成。本文档详细描述了系统的目录结构及其各模块的操作指南。

## 1. 系统详细目录架构

```text
e:\JNU-OPORC\
├── .trae/                      # Trae 编辑器配置目录，包含自定义规则 (Rules)
├── .vercel/                    # Vercel 部署配置文件 (用于云端托管可视化模块)
├── MediaCrawler/               # [核心] 多平台自媒体数据采集引擎
│   ├── api/                    # 爬虫控制 API 与 WebUI 控制台后端
│   │   ├── routers/            # API 路由 (crawler: 任务控制, data: 数据管理, websocket: 实时日志)
│   │   ├── schemas/            # Pydantic 数据验证与模型定义
│   │   ├── services/           # 核心业务逻辑 (如爬虫管理器、任务调度逻辑)
│   │   └── webui/              # 爬虫控制台前端静态资源 (已打包的 JS/CSS/HTML)
│   ├── base/                   # 爬虫抽象基类，定义了统一的抓取行为接口
│   ├── cache/                  # 缓存抽象层 (支持本地文件与 Redis，存储登录态等)
│   ├── config/                 # 采集策略配置中心 (各平台频率限制、登录方式配置)
│   ├── constant/               # 各平台专用的常量与枚举定义
│   ├── database/               # 数据库 ORM 模型与 SQLite/MySQL 连接管理
│   ├── media_platform/         # 各平台爬虫具体实现 (weibo, xhs, dy, bilibili, zhihu, tieba, ks)
│   │   └── [platform]/         # 每个平台包含 client.py, core.py, login.py 等核心实现
│   ├── store/                  # 数据持久化插件 (支持导出为 CSV, Excel 或直接入库)
│   ├── tools/                  # 爬虫辅助工具 (浏览器启动器、Cookie 管理、反爬工具)
│   ├── main.py                 # 爬虫模块命令行入口程序
│   └── requirements.txt        # 爬虫模块独立依赖清单
├── Transformers/               # [智能] 多模态语义分析与标注模块
│   ├── cache/                  # 分析结果哈希缓存 (避免重复分析，节省算力)
│   ├── models/                 # VLM 模型加载器与推理逻辑 (vlm_handler.py)
│   ├── processors/             # 数据处理流水线 (analyzer: 分析, manager: 调度, exporter: 导出)
│   ├── model_weights/          # VLM 模型权重目录 (如 Qwen2-VL, InternVL2)
│   ├── config.py               # 分析流水线全局配置 (Prompt 模板、显存优化参数)
│   ├── main.py                 # 分析模块启动入口 (支持 --stream 流式处理)
│   └── trainer.py              # 模型轻量化微调相关脚本
├── Visualized/                 # [展示] 舆情可视化大屏与管理后台
│   ├── api/                    # 后端核心业务接口 (hotsearch, alerts, dashboard, auth)
│   ├── scripts/                # 运维工具集 (初始化管理员、库表迁移、索引优化)
│   ├── static/                 # 前端静态资源 (全局 CSS、JS 交互)
│   ├── templates/              # Jinja2 动态模板 (Dashboard、预警中心、任务管理页面)
│   ├── app.py                  # 系统主 Web 服务入口 (Port 8000)
│   ├── image_server.py         # 独立图片代理服务器 (解决防盗链与本地存储展示)
│   └── scheduler_manager.py    # 采集任务定时调度管理器
├── Trendradar/                 # [趋势] 趋势分析雷达与 MCP 服务模块
│   ├── mcp_server/             # Model Context Protocol 实现，对接 AI Agent
│   └── main.py                 # 趋势雷达服务启动入口
├── API_DOC.md                  # 系统全量 API 接口详细说明文档
├── README.md                   # 项目整体介绍与快速部署指南
└── requirements.txt            # 项目全局 Python 依赖清单
```

---

## 2. 模块详细文件介绍

### 2.1 MediaCrawler (数据采集引擎)
该模块是系统的“传感器”，负责从各大社交平台获取公开数据。
- **api/**: 暴露 RESTful 接口供 Visualized 模块调用，实现远程启动/停止爬虫。
    - `routers/crawler.py`: 核心路由，接收采集指令。
    - `routers/data.py`: 数据管理路由，支持查询已爬取的数据列表。
    - `routers/websocket.py`: 实时通信路由，用于将爬虫运行日志推送至前端。
    - `services/crawler_manager.py`: 维护爬虫实例池，管理异步采集任务的生命周期。
    - `webui/`: 包含编译后的前端控制台代码，用户可在 8080 端口直接操作。
- **media_platform/**: 包含各平台的深度适配逻辑。
    - `xhs/`: 小红书爬虫，包含 `client.py` (请求封装), `core.py` (业务流程), `login.py` (扫码登录), `xhs_sign.py` (参数签名)。
    - `weibo/`: 微博爬虫，支持热搜同步、指定 ID 内容抓取。
    - `douyin/`: 抖音爬虫，包含 `client.py`, `core.py`, `login.py` 等。
    - `bilibili/`, `kuaishou/`, `zhihu/`, `tieba/`: 其他支持平台的对应实现。
- **base/base_crawler.py**: 爬虫基类，定义了所有平台通用的异步执行逻辑与错误处理。
- **cache/**: 
    - `local_cache.py`: 基于本地文件的 Cookie 与状态持久化。
    - `redis_cache.py`: 基于 Redis 的分布式缓存支持。
- **database/**:
    - `models.py`: 定义了帖子、评论、用户等核心实体模型。
    - `db_session.py`: 数据库连接池与会话管理器。
- **tools/**:
    - `browser_launcher.py`: 基于 Playwright 封装的浏览器启动器，处理 User-Agent 与代理切换。
    - `cookie_cache.py`: 负责登录态的加载与自动续期。
    - `crawler_util.py`: 爬虫通用的辅助函数（如随机延迟、参数生成）。
- **store/**:
    - `excel_store_base.py`: 结构化数据写入 Excel 的基类。
    - `csv_store_base.py`: 结构化数据写入 CSV 的基类。
- **main.py**: 模块统一入口，通过 `--platform` 和 `--type` 参数指定运行模式。

### 2.2 Transformers (智能分析模块)
该模块是系统的“大脑”，负责对原始数据进行定性分析。
- **models/vlm_handler.py**: VLM 推理核心，支持多模态（图文）输入，输出情感分值、关键词。
- **processors/multimodal_analyzer.py**: 封装了具体的业务分析逻辑，如“风险判定”、“舆情分类”。
- **cache/analysis_cache.json**: 记录已分析内容的 ID，系统重启后可断点续传。
- **config.py**: 定义了 AI 的“思考逻辑”（Prompt），可根据需求调整分析维度。

### 2.3 Visualized (可视化管理模块)
该模块是系统的“脸面”，为用户提供交互界面。
- **api/**:
    - `hotsearch.py`: 核心热榜接口，实时采集并聚合 30+ 平台的数据。
    - `alert_engine.py`: 预警逻辑核心，支持基于关键词、情感值和突发流量的复合告警。
    - `alerts.py`: 提供告警列表查询、状态更新及规则管理的 API。
    - `dashboard.py`: 统计分析接口，为大屏展示提供数据支撑。
    - `scheduler.py`: 任务调度器，支持通过前端配置 Cron 表达式启动定时爬取。
    - `auth.py`: 实现用户登录认证、Token 签发与权限校验。
    - `database.py`: 模块内部数据库操作层，负责可视化数据的持久化。
    - `image_server.py`: 专门绕过图片保护机制的代理服务。
- **scripts/**:
    - `setup_admin.py`: 创建初始管理员账号的实用工具。
    - `update_db_schema.py`: 自动检测并升级 SQLite 数据库表结构。
    - `check_perf_indices.py`: 数据库性能分析与索引调优。
- **templates/**:
    - `index.html`: 系统首页，集成舆情统计仪表盘。
    - `hotsearch.html`: 全网热搜看板，支持实时监控。
    - `warning.html`: 预警中心页面，配置告警通知渠道。
    - `crawler.html`: 爬虫控制中心，管理所有下挂的采集任务。
    - `monitor.html`: 热点追踪大图，分析单一事件的演进趋势。
- **app.py**: 系统主入口程序，运行 8000 端口提供全功能的 Web UI。

### 2.4 Trendradar (趋势雷达)
该模块扩展了系统的 AI 能力，使大模型具备本地数据检索能力。
- **mcp_server/**:
    - `server.py`: 基于 FastMCP 框架实现的协议服务器。
    - `services/`: 核心服务逻辑，包含 `data_service.py` (数据检索) 和 `parser_service.py` (结果解析)。
    - `tools/`: 向 LLM 暴露的可调用工具集，如 `analytics.py` (趋势分析)、`data_query.py` (数据库查询)。
    - `utils/`: 通用工具类，包含日期解析与输入验证逻辑。
- **main.py**: 趋势雷达模块的 Web 服务入口。
- **index.html**: 趋势雷达的简易交互界面。

---

---

## 2. Visualized 模块操作手册

**Visualized** 是用户交互的前端门户，负责实时热搜监测、数据聚合展示及预警推送。

### 2.1 核心功能
- **全网热点实时追踪**：支持 30+ 平台（微博、知乎、抖音等）的热搜同步。
- **舆情仪表盘**：可视化展示情感分布、热度趋势及关键词云。
- **预警推送**：自定义关键词监控，支持邮件 SMTP 自动告警。
- **任务调度**：可视化管理定时爬虫任务。

### 2.2 启动方式
```powershell
# 在根目录下运行
uv run --frozen python Visualized/app.py
```
- **Web 访问地址**: `http://localhost:8000`
- **图片服务地址**: `http://localhost:8002` (由 `image_server.py` 提供)

### 2.3 关键配置说明
- **配置文件**: [Visualized/api/config.py](file:///e:/JNU-OPORC/Visualized/api/config.py)
    - `SMTP_SERVER`: 告警邮件服务器地址。
    - `ALL_PLATFORMS`: 系统支持的平台映射表。
    - `PRIORITY_PLATFORMS`: 优先同步的高频热榜平台。

---

## 3. Transformers 模块操作手册

**Transformers** 模块利用大模型 (VLM) 对原始舆情数据进行深度标注与情感判定。

### 3.1 核心功能
- **多模态分析**：同时识别图片内容 (OCR/Object) 与文本情感。
- **双层缓存机制**：通过 `analysis_cache.json` 避免重复分析，大幅节省算力。
- **流式自动处理**：实时检测 `MediaCrawler` 产生的新数据并自动开启分析。

### 3.2 启动方式
#### 3.2.1 手动处理特定日期数据
```powershell
uv run --frozen python Transformers/main.py --date 2026-03-06 --platform weibo
```

#### 3.2.2 开启流式自动标注 (推荐)
```powershell
uv run --frozen python Transformers/main.py --stream --source_type sqlite
```
*提示：开启流式模式后，系统每隔 60 秒检查一次数据库，处理未标注的新记录。*

### 3.3 显存优化与模型配置
- **模型权重**: 存放在 `Transformers/model_weights/`。
- **显存支持**: 默认开启 4-bit 量化，支持 6GB 显存运行 `Qwen2-VL-2B`。
- **离线模式**: 默认开启 `TRANSFORMERS_OFFLINE=1`，确保在无网环境下稳定运行。

---

## 4. 模块协作流程

1. **采集**: 通过 `Visualized` 后台下发任务，由 `MediaCrawler` 执行数据抓取，结果存入 `MediaCrawler/data/` 或 SQLite 数据库。
2. **分析**: `Transformers` 监测到新数据，调用 VLM 进行情感标注与意图识别，结果回填至数据库。
3. **展示**: `Visualized` 仪表盘读取标注后的数据，生成可视化图表。
4. **预警**: 若分析结果命中高风险关键词，`Visualized` 自动触发告警逻辑。
