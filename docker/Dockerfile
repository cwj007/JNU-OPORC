# 使用 Microsoft 提供的 Playwright 镜像作为基础镜像
# 它已经预装了所有浏览器运行时及其依赖，这对于 MediaCrawler 至关重要
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    UV_SYSTEM_PYTHON=1 \
    # 启用 Playwright 的无头模式
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 安装系统级依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv (Python 依赖管理工具)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# 首先复制依赖文件以便利用 Docker 缓存
COPY pyproject.toml uv.lock ./

# 使用 uv 导出并安装依赖
# 我们排除 windows 平台特有的 source，让 uv 自动解析 linux 平台的依赖 (如 torch)
RUN uv pip install --system --index-url https://mirrors.aliyun.com/pypi/simple/ \
    "fastapi" "uvicorn" "playwright==1.45.0" "pandas" "aiosqlite" "redis" "jinja2" \
    "python-dotenv" "aiofiles" "pydantic" "tenacity" "typer" "opencv-python-headless" \
    "aiomysql" "parsel" "pyexecjs" "pyhumps" "cryptography" "alembic" "asyncmy" \
    "sqlalchemy" "motor" "openpyxl" "requests" "pytz" "PyYAML" "websockets" \
    "jieba" "wordcloud" "matplotlib" "python-multipart" "passlib[bcrypt]" "python-jose[cryptography]"

# 如果需要支持 Transformers 模块，可以额外安装 torch 等 (可选，默认不安装以减小体积)
# RUN uv pip install --system torch torchvision transformers

# 复制项目代码
COPY . .

# 暴露服务端口
# 8080: MediaCrawler API
# 8000: Visualized Dashboard
# 8002: Image Server
EXPOSE 8080 8000 8002

# 默认启动脚本
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
