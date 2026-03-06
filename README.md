# JNU-OPORC (舆情监测与分析平台)

本项是一个综合性的舆情监测与分析系统，包含数据采集、多模态情感分析、可视化展示与实时告警等功能。

## 1. 核心模块说明

### 1.1 MediaCrawler (数据采集模块)
[MediaCrawler](file:///e:/JNU-OPORC/MediaCrawler) 是系统的核心数据获取引擎，支持主流社交媒体平台的自动化采集。
- **主要功能**: 
  - 支持小红书、抖音、快手、B站、微博、贴吧、知乎等平台的采集。
  - 提供搜索模式、详情模式、创作者模式等多种采集策略。
  - 支持实时日志监控与可视化任务控制。
- **核心技术**: 
  - **Playwright**: 基于浏览器自动化的动态数据抓取。
  - **FastAPI**: 提供 RESTful API 用于 WebUI 控制。
  - **Pandas**: 数据处理与多格式（JSON, CSV, XLSX）导出。
  - **Database**: 支持 SQLite, Redis, MongoDB 等多种存储后端。

### 1.2 Transformers (智能分析模块)
[Transformers](file:///e:/JNU-OPORC/Transformers) 模块负责对采集到的原始数据进行深度的语义和多模态分析。
- **主要功能**:
  - **多模态分析**: 结合文本与图像信息进行深度理解。
  - **情感分析**: 自动识别舆情数据的正面、负面或中性情感倾向。
  - **数据标注**: 为训练数据提供自动化的标注流水线。
  - **流式处理**: 支持从数据库中实时读取新数据并进行动态分析。
- **核心技术**:
  - **PyTorch & Transformers**: 基于深度学习的大规模预训练模型推理。
  - **VLM (Vision-Language Models)**: 用于多模态内容的联合理解。
  - **DataManager**: 复杂的数据加载、过滤与清洗逻辑。

### 1.3 Visualized (可视化与告警模块)
[Visualized](file:///e:/JNU-OPORC/Visualized) 是用户交互的前端门户，集成了管理后台与可视化大屏。
- **主要功能**:
  - **热点监测**: 实时追踪全网热搜排名与变化趋势。
  - **舆情仪表盘**: 以图表形式展示情感分布、数据量趋势等。
  - **任务调度**: 内置任务调度器，支持定时触发爬虫与分析任务。
  - **实时告警**: 异常舆情自动触发系统告警。
- **核心技术**:
  - **FastAPI**: 高性能的后端 API 服务。
  - **Vue 3 (Composition API)**: 前端采用 Vue 3 组合式 API 进行数据驱动与交互。
  - **Element Plus**: 配套的 UI 组件库。
  - **Jinja2**: 服务器端渲染的交互式页面。
  - **SQLite**: 本地高效的热点数据与告警信息存储。
  - **WebSocket**: 实现实时日志流推送。
  - **Image Server (8002 端口)**: 独立的静态资源与实时缩略图服务，确保前端图片加载的高性能。

## 2. 快速部署 (Docker)

本系统支持使用 Docker 进行快速一键部署。所有的 Docker 相关配置文件均位于 `docker` 文件夹中。

### 2.1 部署步骤

1. **环境准备**: 确保已安装 Docker 和 Docker Compose。
2. **启动服务**:
   ```bash
   # 进入项目根目录
   cd JNU-OPORC
   # 使用 docker-compose 启动所有服务
   docker compose -f docker/docker-compose.yml up -d
   ```
3. **访问系统**:
   - **可视化控制台**: [http://localhost:8000](http://localhost:8000)
   - **采集控制 API**: [http://localhost:8080](http://localhost:8080)
   - **图片资源服务**: [http://localhost:8002](http://localhost:8002)

### 2.2 服务说明

- **visualized**: 主控制面板，整合了数据展示与任务调度。
- **mediacrawler**: 核心采集服务，负责与社交媒体平台交互。
- **redis**: 用于系统缓存与任务队列。

## 3. API 接口文档

详细的系统目录架构、操作手册及模块协作指南，请参阅：
[JNU-OPORC 系统结构与操作手册 (SYSTEM_STRUCTURE.md)](file:///e:/JNU-OPORC/SYSTEM_STRUCTURE.md)

### 2.1 采集控制 API (MediaCrawler)
| 接口地址 | 方法 | 功能描述 |
| :--- | :--- | :--- |
| `/api/crawler/start` | POST | 启动指定的爬虫任务 |
| `/api/crawler/stop` | POST | 停止当前运行的爬虫任务 |
| `/api/crawler/status` | GET | 获取当前爬虫的运行状态 |
| `/api/crawler/logs` | GET | 获取最新的采集日志 |
| `/api/ws/logs` | WS | 实时日志流推送 |

### 2.2 数据管理 API (MediaCrawler)
| 接口地址 | 方法 | 功能描述 |
| :--- | :--- | :--- |
| `/api/data/files` | GET | 列出所有采集到的数据文件 |
| `/api/data/files/{path}` | GET | 预览数据文件内容 |
| `/api/data/download/{path}` | GET | 下载采集到的原始数据文件 |
| `/api/data/stats` | GET | 获取采集数据的统计信息 |

### 2.3 可视化与监控 API (Visualized)
| 接口地址 | 方法 | 功能描述 |
| :--- | :--- | :--- |
| `/api/hotsearch/all` | GET | 获取全网热搜列表 |
| `/api/hotsearch/data/{id}`| GET | 获取特定热搜词的详细分析数据 |
| `/api/alerts/list` | GET | 获取系统触发的实时告警列表 |
| `/api/scheduler/list` | GET | 查看当前定时任务列表 |
| `/api/scheduler/add` | POST | 添加新的定时采集/分析任务 |

## 3. 技术栈汇总

- **开发语言**: Python 3.10+, JavaScript
- **前端框架**: Vue 3 (Composition API), Element Plus
- **Web 框架**: FastAPI, Jinja2
- **自动化工具**: Playwright
- **AI/ML**: PyTorch, Transformers (VLM), HuggingFace
- **数据处理**: Pandas, NumPy
- **数据库**: SQLite(主要), Redis, MongoDB, MySQL
- **环境管理**: uv (Python 依赖管理工具)
