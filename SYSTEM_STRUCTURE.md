# JNU-OPORC 系统目录架构与操作手册

本仓库是一个综合性的舆情监测与分析系统，由数据采集、智能分析和可视化管理三大核心模块组成。本文档详细描述了系统的目录结构及其各模块的操作指南。

## 1. 系统详细目录架构

```text
e:\JNU-OPORC\
├── .trae/                      # Trae 编辑器配置与规则
├── .vercel/                    # Vercel 部署相关配置
├── MediaCrawler/               # [核心] 数据采集模块 (独立引擎)
│   ├── api/                    # 爬虫控制 API 与 WebUI 服务
│   │   ├── routers/            # 路由定义 (爬虫控制、数据管理、WebSocket)
│   │   ├── schemas/            # Pydantic 数据模型
│   │   ├── services/           # 核心业务逻辑 (爬虫管理服务)
│   │   └── webui/              # 爬虫可视化控制台前端
│   ├── base/                   # 爬虫基类定义
│   ├── cache/                  # 缓存实现 (本地、Redis 等)
│   ├── config/                 # 各平台采集配置 (weibo, zhihu, xhs, dy 等)
│   ├── database/               # 数据库模型与存储逻辑 (SQLite, MongoDB)
│   ├── media_platform/         # 各平台具体爬虫实现 (核心抓取代码)
│   ├── store/                  # 数据持久化逻辑 (CSV, Excel, Database)
│   ├── tools/                  # 爬虫工具类 (浏览器启动器、Cookie 管理等)
│   ├── main.py                 # 爬虫模块入口
│   └── requirements.txt        # 爬虫模块依赖
├── Transformers/               # [智能] 多模态分析模块
│   ├── cache/                  # 分析结果与上下文缓存
│   ├── models/                 # VLM 模型加载与推理逻辑 (vlm_handler.py)
│   ├── processors/             # 数据处理器 (analyzer, data_manager, exporter)
│   ├── model_weights/          # VLM 模型权重存放目录 (如 Qwen2-VL)
│   ├── config.py               # 分析流水线配置 (Prompt 模板、显存优化)
│   ├── main.py                 # 分析流水线启动入口 (支持流式处理)
│   └── trainer.py              # 模型微调相关脚本
├── Visualized/                 # [展示] 可视化与管理模块
│   ├── api/                    # 后端 API 接口 (hotsearch, alerts, dashboard)
│   ├── logos/                  # 各大平台图标资源
│   ├── static/                 # 静态资源 (CSS, JS)
│   ├── templates/              # Jinja2 网页模板 (Dashboard, Hotsearch)
│   ├── app.py                  # 系统主 Web 服务入口
│   ├── image_server.py         # 独立的图片代理服务器 (8002 端口)
│   └── scheduler_manager.py    # 任务调度管理
├── Trendradar/                 # 趋势分析与 MCP 服务模块
├── API_DOC.md                  # 详细 API 接口文档
├── README.md                   # 项目概览
└── requirements.txt            # 项目整体依赖
```

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
