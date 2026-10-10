# JNU-OPORC 舆情监测与分析平台

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110.2-green)
![Vue](https://img.shields.io/badge/Vue-3.x-4FC08D)
![License](https://img.shields.io/badge/License-Non--Commercial-yellow)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

</div>

## 📖 项目简介

JNU-OPORC 是一个集 **多平台数据采集**、**多模态智能分析**、**可视化舆情监控** 于一体的综合性舆情监测系统。项目由三大核心模块协同工作，实现从原始数据采集、AI 深度分析到可视化展示与实时告警的完整舆情分析闭环。

### ✨ 核心亮点

- 🌐 **多平台覆盖**：支持小红书、抖音、快手、B站、微博、贴吧、知乎等 7+ 主流社交媒体平台
- 🤖 **多模态 AI 分析**：基于 Qwen2-VL 视觉语言模型，实现图文联合情感分析与意图识别
- 📊 **30+ 热搜平台监测**：实时追踪全网热点动态，一键掌握舆情脉搏
- 🔔 **智能告警引擎**：支持关键词、情感极性、突发流量等多维度复合告警
- ⏰ **任务调度中心**：可视化配置定时采集任务，自动化运维无忧
- 🐳 **Docker 一键部署**：开箱即用，快速搭建完整舆情监测环境

---

## 🏗️ 系统架构

<!-- 内容展示：到时候我会自己上传图片（系统架构图） -->

系统采用模块化分层架构，三大核心模块通过数据库和 API 接口松耦合协作：

| 层级 | 模块 | 职责 | 核心技术 |
| :--- | :--- | :--- | :--- |
| 采集层 | **MediaCrawler** | 多平台数据抓取与存储 | Playwright, FastAPI, SQLite/Redis/MongoDB |
| 分析层 | **Transformers** | 多模态情感分析与数据标注 | PyTorch, Qwen2-VL, 4-bit 量化推理 |
| 展示层 | **Visualized** | 可视化大屏、任务调度、告警推送 | Vue 3, Element Plus, Jinja2, WebSocket |
| 扩展层 | **Trendradar** | 趋势分析雷达 + MCP AI Agent 服务 | FastMCP, YAML 配置驱动 |

---

## 🎯 功能特性

### 1. 多平台数据采集 (MediaCrawler)

<!-- 内容展示：到时候我会自己上传图片（数据采集模块界面截图） -->

| 功能 | 说明 |
| :--- | :--- |
| **7 大平台支持** | 小红书 (xhs)、抖音 (dy)、快手 (ks)、Bilibili (bili)、微博 (wb)、百度贴吧 (tieba)、知乎 (zhihu) |
| **多种采集模式** | 搜索模式（关键词）、详情模式（指定ID）、创作者模式（用户主页） |
| **登录方式** | 二维码扫码登录 / Cookie 登录 |
| **数据导出格式** | JSON / CSV / Excel (XLSX) / SQLite / MySQL / MongoDB |
| **代理 IP 池** | 集成豌豆 HTTP、快代理、极速 HTTP 等多家代理服务商 |
| **缓存策略** | 本地文件缓存 / Redis 分布式缓存，支持 Cookie 自动续期 |
| **WebUI 控制台** | 可视化任务控制 + 实时日志流 WebSocket 推送 |

### 2. 多模态智能分析 (Transformers)

<!-- 内容展示：到时候我会自己上传图片（智能分析模块输出示例） -->

| 功能 | 说明 |
| :--- | :--- |
| **视觉语言模型** | 基于 Qwen2-VL-2B-Instruct，支持图文联合理解 |
| **三档情感分类** | 正面 / 中性 / 负面 情感极性判定 |
| **细粒度情感标签** | 惊喜、赞赏、愤怒、失望等 15+ 细分情感标签 |
| **意图识别** | 推荐安利、吐槽不满、咨询围观等多维度意图分类 |
| **反讽检测** | 识别图文不符、反话正说等复杂反讽表达 |
| **关键词提取** | 自动提取 3-5 个核心关键词，自动生成视觉对象列表 |
| **OCR 文字识别** | 自动识别图片中的文字内容辅助分析 |
| **4-bit 量化加速** | 6GB 显存即可流畅运行，推理速度优化极致 |
| **流式处理模式** | 实时监听数据库新数据，自动增量分析 |
| **断点续分析** | 分析结果哈希缓存，重启后自动跳过已处理内容 |

### 3. 可视化监控大屏 (Visualized)

<!-- 内容展示：到时候我会自己上传图片（可视化大屏截图） -->

| 功能 | 说明 |
| :--- | :--- |
| **全网热搜看板** | 聚合 30+ 平台实时热搜榜单，支持历史趋势回溯 |
| **舆情仪表盘** | 情感分布饼图、热度趋势折线图、词云图等多维图表 |
| **热点追踪详情** | 单事件维度：时间演进、评论情感走势、关键观点提取 |
| **数据量排行** | 各平台采集量、互动量排行可视化 |
| **爬虫控制中心** | 远程下发采集任务 + 实时状态监控 |
| **任务调度系统** | Cron 表达式配置定时任务，支持采集/分析/热搜同步 |
| **智能告警中心** | 关键词命中 + 负面情感 + 流量突增 三维度复合告警规则 |
| **用户权限管理** | 管理员/普通用户分级访问控制 |
| **独立图片服务** | 8002 端口图片代理服务，绕过防盗链，缩略图高性能加载 |

---

## 📦 项目目录结构

```text
JNU-OPORC/
├── MediaCrawler/               # [采集层] 多平台数据采集引擎
│   ├── api/                    # FastAPI 控制接口 + WebUI 前端
│   │   ├── routers/            # crawler/data/websocket 三大路由
│   │   ├── services/           # 爬虫管理器、任务生命周期
│   │   └── webui/              # 前端控制台（已打包）
│   ├── base/                   # 爬虫抽象基类
│   ├── cache/                  # 本地/Redis 缓存抽象层
│   ├── config/                 # 各平台频率限制、登录配置
│   ├── database/               # SQLAlchemy ORM + 多数据库支持
│   ├── media_platform/         # 7 大平台爬虫具体实现
│   │   ├── xhs/dy/ks/bili/     # 每个平台独立目录
│   │   ├── wb/tieba/zhihu/     # client/core/login 三件套
│   ├── proxy/                  # 代理 IP 池 + 多家服务商适配
│   ├── store/                  # CSV/Excel/SQLite 数据持久化
│   ├── tools/                  # 浏览器启动、Cookie、反爬工具
│   └── main.py                 # 命令行入口
│
├── Transformers/               # [分析层] 多模态 AI 分析流水线
│   ├── models/                 # VLM 模型加载与推理核心
│   │   └── vlm_handler.py      # Qwen2-VL 推理封装
│   ├── processors/             # 数据处理流水线
│   │   ├── data_manager.py     # 数据加载、过滤、清洗
│   │   ├── multimodal_analyzer.py  # 业务分析逻辑
│   │   └── exporter.py         # 多格式结果导出
│   ├── cache/                  # 已分析内容哈希缓存
│   ├── model_weights/          # 模型权重存放目录
│   ├── config.py               # Prompt 模板、显存优化参数
│   └── main.py                 # 分析入口（支持 --stream 流式）
│
├── Visualized/                 # [展示层] 可视化大屏与管理后台
│   ├── api/                    # 后端业务接口
│   │   ├── hotsearch.py        # 30+ 平台热搜聚合
│   │   ├── alert_engine.py     # 告警规则匹配引擎
│   │   ├── alerts.py           # 告警管理 API
│   │   ├── dashboard.py        # 仪表盘统计数据
│   │   ├── scheduler.py        # 定时任务调度
│   │   ├── auth.py             # JWT 登录认证
│   │   └── crawler_ext.py      # MediaCrawler 集成扩展
│   ├── templates/              # Jinja2 动态页面模板
│   │   ├── index.html          # 舆情仪表盘首页
│   │   ├── hotsearch.html      # 全网热搜看板
│   │   ├── crawler.html        # 爬虫控制中心
│   │   ├── monitor.html        # 热点事件追踪
│   │   ├── warning.html        # 告警中心
│   │   └── login.html          # 用户登录页
│   ├── scripts/                # 运维脚本（建库、迁移、索引）
│   ├── logos/                  # 各平台 Logo 资源
│   ├── app.py                  # 主服务入口 (Port 8000)
│   ├── image_server.py         # 图片代理服务 (Port 8002)
│   └── scheduler_manager.py    # 任务调度管理器
│
├── Trendradar/                 # [扩展] 趋势雷达 + MCP 服务
│   └── mcp_server/             # FastMCP AI Agent 接入
│
├── docker/                     # Docker 部署配置
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── entrypoint.sh
│
├── API_DOC.md                  # 完整 API 接口文档
├── SYSTEM_STRUCTURE.md         # 系统架构与操作手册
├── 项目启动文档.md              # 本地开发启动指南
└── pyproject.toml              # 全局 Python 依赖 (uv 管理)
```

---

## 🚀 快速部署

### 方式一：Docker Compose 一键部署（推荐）

#### 前置要求

- Docker 20.10+
- Docker Compose v2+

#### 启动步骤

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd JNU-OPORC

# 2. 使用 docker-compose 启动所有服务
docker compose -f docker/docker-compose.yml up -d

# 3. 查看服务状态
docker compose -f docker/docker-compose.yml ps
```

#### 访问地址

| 服务 | 地址 | 说明 |
| :--- | :--- | :--- |
| **可视化控制台** | http://localhost:8000 | 舆情大屏 + 任务调度 + 告警中心 |
| **采集控制 API** | http://localhost:8080 | MediaCrawler 采集服务 WebUI |
| **图片资源服务** | http://localhost:8002 | 爬取图片代理与缩略图服务 |
| **Redis** | localhost:6379 | 缓存与任务队列（内部使用） |

#### 服务说明

```text
┌─────────────────────────────────────────────────────┐
│                  Docker Network                      │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────┐ │
│  │  Visualized  │──▶│    Redis     │◀──│  Media  │ │
│  │  (Port 8000) │   │ (Port 6379)  │   │ Crawler │ │
│  │  (Port 8002) │   └──────────────┘   │(Port8080)│ │
│  └──────────────┘                      └─────────┘ │
└─────────────────────────────────────────────────────┘
```

---

### 方式二：本地开发环境部署

#### 环境要求

| 组件 | 版本要求 | 备注 |
| :--- | :--- | :--- |
| **操作系统** | Windows 10/11 | 项目基于 Windows 环境开发 |
| **Python** | >= 3.10, < 3.11 | 全局使用 [uv](https://github.com/astral-sh/uv) 管理依赖 |
| **Node.js** | >= 16.0.0 | 部分爬虫 JS 签名依赖 |
| **NVIDIA GPU** | 显存 >= 6GB | Transformers 模块可选，纯 CPU 可运行但较慢 |
| **CUDA Toolkit** | 12.1+ | GPU 加速 PyTorch 推理 |

#### 安装 uv 包管理器

```powershell
# Windows PowerShell 安装 uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 验证安装
uv --version
```

#### 第一步：安装全局依赖

```powershell
cd JNU-OPORC

# 使用 uv 同步全局依赖（使用阿里云镜像加速）
uv sync
```

#### 第二步：部署 MediaCrawler（数据采集）

```powershell
cd MediaCrawler

# 1. 同步模块依赖
uv sync

# 2. 安装 Playwright 浏览器驱动（首次必做）
uv run --frozen playwright install

# 3. 配置环境变量（如需 MySQL/Redis/MongoDB）
copy .env.example .env
# 编辑 .env 填入数据库密码、代理 Key 等

# 4. 启动采集 API 服务（推荐）
uv run --frozen uvicorn api.main:app --port 8080

# 或使用命令行模式直接采集
# 示例：爬取微博关键词搜索结果
uv run --frozen main.py --platform wb --type search
```

启动后访问 **http://localhost:8080** 打开采集控制台：

<!-- 内容展示：到时候我会自己上传图片（MediaCrawler WebUI 控制台截图） -->

#### 第三步：部署 Transformers（智能分析）

```powershell
cd ../Transformers

# 1. 同步依赖（已在根目录 uv sync 则可跳过）
# uv sync

# 2. 首次运行：临时关闭离线模式下载模型
# 编辑 config.py 将 TRANSFORMERS_OFFLINE 临时改为 "0"，
# 或在命令行设置环境变量：
# $env:TRANSFORMERS_OFFLINE="0"

# 3. 处理指定日期的数据（示例：微博 + CSV 数据源）
uv run --frozen main.py --date 2026-01-01 --platform weibo --source_type csv

# 4. 启用流式处理（推荐生产环境，实时分析新采集数据）
uv run --frozen main.py --stream --platform weibo --stream_interval 60
```

**分析结果示例：**

<!-- 内容展示：到时候我会自己上传图片（分析结果 JSON 示例截图） -->

每条数据输出以下结构化字段：
```json
{
  "content_id": "xxx",
  "sentiment": "负面",
  "fine_grained_sentiment": "愤怒",
  "intent": "投诉反馈",
  "irony_detected": false,
  "reasoning": "用户对XX产品售后体验不满，使用强烈指责措辞...",
  "keywords": ["售后", "推诿", "退款"],
  "objects": ["手机截图", "订单号"],
  "ocr_text": "订单号: 123456789..."
}
```

#### 第四步：部署 Visualized（可视化大屏）

```powershell
cd ../Visualized

# 1. 初始化 SQLite 数据库表结构
uv run --frozen python scripts/setup_admin.py  # 创建初始管理员账号
uv run --frozen python test/run_init_db.py    # 初始化库表

# 2. 启动图片代理服务（后台运行，端口 8002）
uv run --frozen python image_server.py

# 3. 启动主可视化服务（端口 8000，新开终端）
uv run --frozen uvicorn app:app --port 8000 --reload
```

访问 **http://localhost:8000** 进入舆情监控系统登录页：

<!-- 内容展示：到时候我会自己上传图片（系统登录页截图） -->

登录后进入舆情仪表盘首页：

<!-- 内容展示：到时候我会自己上传图片（舆情仪表盘首页截图） -->

---

## ⚙️ 配置说明

### MediaCrawler 环境变量

复制 `MediaCrawler/.env.example` 为 `.env`，根据需要配置：

| 变量名 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `MYSQL_DB_*` | MySQL 数据库连接配置 | localhost / 3306 |
| `REDIS_DB_*` | Redis 缓存连接配置 | 127.0.0.1 / 6379 |
| `MONGODB_*` | MongoDB 数据库配置 | localhost / 27017 |
| `POSTGRES_*` | PostgreSQL 配置 | localhost / 5432 |
| `WANDOU_APP_KEY` | 豌豆代理 AppKey（可选） | 空 |
| `KDL_*` | 快代理认证信息（可选） | 空 |
| `jisu_key` / `jisu_crypto` | 极速代理 Key（可选） | 空 |

### Transformers 核心配置

编辑 [Transformers/config.py](file:///e:/JNU-OPORC/Transformers/config.py) 调整：

| 配置项 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `VLM_MODEL_ID` | 使用的 VLM 模型 | `qwen/Qwen2-VL-2B-Instruct` |
| `DEVICE` | 推理设备 | `cuda` 优先，回退 `cpu` |
| `USE_4BIT` | 是否启用 4-bit 量化 | `True`（6GB 显存必须开启） |
| `MAX_IMAGES_FOR_VLM` | 单条数据最多分析图片数 | 9 张 |
| `MAX_SEQ_LENGTH` | 最大 Token 序列长度 | 2048 |
| `TRANSFORMERS_OFFLINE` | 离线模式（模型下载完成后开启） | `1` |

### Visualized 关键配置

| 配置文件 | 说明 |
| :--- | :--- |
| [Visualized/api/config.py](file:///e:/JNU-OPORC/Visualized/api/config.py) | 告警 SMTP 服务器、平台映射、告警规则阈值等 |
| [Visualized/api/scheduler_config.json](file:///e:/JNU-OPORC/Visualized/api/scheduler_config.json) | 定时任务调度配置持久化 |

---

## 📚 完整文档导航

| 文档 | 路径 | 说明 |
| :--- | :--- | :--- |
| **系统架构手册** | [SYSTEM_STRUCTURE.md](file:///e:/JNU-OPORC/SYSTEM_STRUCTURE.md) | 详细目录结构、各文件职责、模块协作指南 |
| **API 接口文档** | [API_DOC.md](file:///e:/JNU-OPORC/API_DOC.md) | 全部 RESTful 接口参数与返回示例 |
| **本地启动指南** | [项目启动文档.md](file:///e:/JNU-OPORC/项目启动文档.md) | 开发环境逐步启动说明与注意事项 |

---

## 🔌 核心 API 速览

### MediaCrawler 采集控制 API

| 接口 | 方法 | 功能 |
| :--- | :--- | :--- |
| `/api/crawler/start` | POST | 启动指定爬虫任务（平台/模式/关键词） |
| `/api/crawler/stop` | POST | 停止当前运行的爬虫任务 |
| `/api/crawler/status` | GET | 获取爬虫运行状态与进度 |
| `/api/crawler/logs` | GET | 拉取最近 N 条采集日志 |
| `/api/ws/logs` | WS | WebSocket 实时日志流推送 |
| `/api/data/files` | GET | 列出已采集的数据文件 |
| `/api/data/download/{path}` | GET | 下载原始数据文件 |
| `/api/data/stats` | GET | 采集数据量统计概览 |
| `/config/platforms` | GET | 获取支持的平台列表 |
| `/config/options` | GET | 获取采集配置选项枚举 |

### Visualized 可视化 API

| 接口 | 方法 | 功能 |
| :--- | :--- | :--- |
| `/api/hotsearch/all` | GET | 全网热搜列表（支持分页/平台过滤） |
| `/api/hotsearch/data/{id}` | GET | 单热搜词详细分析数据 |
| `/api/dashboard/stats` | GET | 仪表盘全局统计（情感分布/采集量等） |
| `/api/alerts/list` | GET | 告警列表（支持状态/级别/时间过滤） |
| `/api/alerts/rules` | GET/POST | 告警规则管理（增删改查） |
| `/api/scheduler/list` | GET | 定时任务列表 |
| `/api/scheduler/add` | POST | 新增定时采集/分析任务（Cron 表达式） |
| `/api/scheduler/toggle` | POST | 启用/禁用指定定时任务 |
| `/api/auth/login` | POST | 用户登录获取 JWT Token |
| `/api/monitor/track/{topic}` | GET | 单话题舆情演进趋势数据 |

---

## 🧪 测试说明

项目遵循 **测试代码写入对应模块 test 目录** 的规范：

```bash
# 运行 MediaCrawler 单元测试
cd MediaCrawler
uv run --frozen pytest test/ -v

# 运行 Transformers 模块测试
cd Transformers
uv run --frozen pytest test/ -v

# 运行 Visualized 接口测试
cd Visualized
uv run --frozen pytest test/test_api.py -v
```

---

## 🛠️ 技术栈汇总

### 后端技术

| 类别 | 技术选型 |
| :--- | :--- |
| **Web 框架** | FastAPI 0.110.2, Uvicorn 0.29.0 |
| **数据库** | SQLite（主力）、MySQL、MongoDB、PostgreSQL |
| **缓存中间件** | Redis 4.6.x |
| **爬虫自动化** | Playwright 1.45.0 + 自定义 JS 签名 |
| **AI/ML 框架** | PyTorch 2.4+ (CUDA 12.1), Transformers 4.45+ |
| **VLM 模型** | Qwen2-VL-2B-Instruct (4-bit 量化) |
| **数据处理** | Pandas 2.2.3, NumPy, Jieba 分词 |
| **序列化/校验** | Pydantic 2.x, SQLAlchemy 2.0 ORM |
| **认证授权** | python-jose (JWT) + passlib (bcrypt) |
| **异步支持** | asyncio, aiofiles, aiomysql, asyncpg |
| **包管理** | uv（取代 pip/poetry，极速依赖解析） |

### 前端技术

| 类别 | 技术选型 |
| :--- | :--- |
| **前端框架** | Vue 3 (Composition API) |
| **UI 组件库** | Element Plus |
| **SSR 模板** | Jinja2（部分页面后端渲染） |
| **实时通信** | WebSocket（日志流、告警推送） |
| **图表可视化** | ECharts / Matplotlib 生成图 |
| **词云生成** | wordcloud 1.9.3 |

### 运维部署

| 类别 | 技术选型 |
| :--- | :--- |
| **容器化** | Docker + Docker Compose |
| **进程管理** | 容器 restart 策略 + 定时调度内置 |
| **CI/CD** | 支持 Vercel 部署 Visualized 模块 |

---

## ❓ 常见问题 FAQ

### Q1: Playwright 安装失败或浏览器无法启动？

```powershell
# 1. 确保已安装 Playwright 依赖
uv run --frozen playwright install-deps

# 2. 如果报错缺少 VC++ 运行库，安装 Visual C++ Redistributable
```

### Q2: Transformers 模块显存不足 (CUDA Out of Memory)？

- 确保 `USE_4BIT = True` 已开启 4-bit 量化
- 调小 `--batch_size` 参数（如从 16 改为 4 或 2）
- 减少 `MAX_IMAGES_FOR_VLM`（如从 9 改为 3）
- 如果仍不足，设置 `DEVICE = "cpu"` 改用 CPU 推理

### Q3: 模型下载速度极慢或失败？

```powershell
# 1. 确认已配置 HF 镜像（config.py 中已默认设置）
#    HF_ENDPOINT = "https://hf-mirror.com"

# 2. 临时关闭离线模式允许下载
$env:TRANSFORMERS_OFFLINE="0"
$env:HF_HUB_OFFLINE="0"

# 3. 运行一次分析触发下载后，再改回离线模式
```

### Q4: Windows 控制台中文/Emoji 乱码？

确保终端编码为 UTF-8：
```powershell
# 临时设置当前终端
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001
```
或使用 Windows Terminal（默认支持 UTF-8）而非旧版 cmd。

### Q5: 爬虫登录态频繁失效？

检查以下几点：
1. 账号是否触发风控（建议使用小号）
2. 采集频率是否过高（在 `config/*_config.py` 中调大 `CRAWLER_INTERVAL`）
3. 代理 IP 是否被封禁（启用代理 IP 池轮换）
4. `cache/cookie_cache` 目录权限是否正常

---

## 📜 免责声明与使用许可

> ⚠️ **重要提示**：本项目仅供 **学习和研究** 目的使用。使用者须遵守以下原则：
>
> 1. **禁止商业用途**：不得将本代码及其产生的数据用于任何商业场景。
> 2. **遵守平台规则**：使用时须遵守目标平台的《用户协议》和 `robots.txt` 规则。
> 3. **合理控制频率**：严禁大规模爬取或对目标平台服务器造成运营干扰。
> 4. **合规使用数据**：不得利用采集数据从事任何非法或不正当行为。
> 5. **责任自负**：使用者对其使用本项目的一切行为及后果承担全部法律责任。

详细许可条款请参阅各模块内的 `LICENSE` 文件。使用本代码即视为您已阅读并同意上述条款。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request 共同改进项目！

提交 PR 前请确保：
1. 代码注释全部使用 **中文** 注释（遵循项目规则）
2. 新增功能配套写入对应模块的 `test/` 目录
3. 代码中不使用绝对路径，全部使用相对路径
4. 通过现有单元测试：`uv run --frozen pytest`

---

## 📬 联系与致谢

- 项目作者：**JJ_Superman** (JNU-OPORC Team)
- GitHub 仓库：`https://github.com/cwj007/JNU-OPORC`

本项目在开发过程中参考/使用了以下优秀开源项目，在此致以诚挚感谢：

| 项目 | 说明 |
| :--- | :--- |
| [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 多平台爬虫框架基础 |
| [QwenLM/Qwen2-VL](https://github.com/QwenLM/Qwen2-VL) | 视觉语言大模型 |
| [HuggingFace Transformers](https://github.com/huggingface/transformers) | 模型推理框架 |
| [fastapi-mcp](https://github.com/jlowin/fastmcp) | MCP 协议实现 |
| [Astral UV](https://github.com/astral-sh/uv) | 极速 Python 包管理 |

---

<div align="center">

**若本项目对您有帮助，欢迎点一个 ⭐ Star 支持作者！**

Made with ❤️ by JNU-OPORC Team

</div>
