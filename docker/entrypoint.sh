#!/bin/bash
set -e

# 设置工作目录
cd /app

# 根据环境变量启动不同服务
if [ "$SERVICE_TYPE" = "mediacrawler" ]; then
    echo "Starting MediaCrawler API Server on port 8080..."
    # 确保在 MediaCrawler 目录中运行
    cd /app/MediaCrawler
    uv run --frozen python -m api.main --port 8080 --host 0.0.0.0

elif [ "$SERVICE_TYPE" = "visualized" ]; then
    echo "Starting Visualized Dashboard on port 8000..."
    # 启动 Image Server (8002 端口)
    cd /app/Visualized
    uv run --frozen python image_server.py --port 8002 --host 0.0.0.0 &
    
    # 启动主应用
    echo "Starting Visualized main app..."
    uv run --frozen python app.py --port 8000 --host 0.0.0.0

elif [ "$SERVICE_TYPE" = "transformers" ]; then
    echo "Starting Transformers Analysis Pipeline (Stream mode)..."
    cd /app/Transformers
    uv run --frozen python main.py --stream --platform weibo

else
    # 默认启动 Visualized，因为它整合了大部分功能
    echo "Starting JNU-OPORC (Visualized All-in-One)..."
    # 同时启动 8002 端口的 image server
    cd /app/Visualized
    uv run --frozen python image_server.py --port 8002 --host 0.0.0.0 &
    
    echo "Starting Visualized dashboard..."
    uv run --frozen python app.py --port 8000 --host 0.0.0.0
fi
