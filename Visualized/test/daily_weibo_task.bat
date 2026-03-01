@echo off
setlocal enabledelayedexpansion

:: 设置 UTF-8 编码
chcp 65001 >nul

echo ============================================================
echo [%date% %time%] 开始执行微博每日定时任务...
echo ============================================================

:: 进入 MediaCrawler 目录
cd /d "e:\JNU-OPORC\MediaCrawler"
if %errorlevel% neq 0 (
    echo [错误] 找不到目录: e:\JNU-OPORC\MediaCrawler
    exit /b 1
)

echo [1/2] 正在提取微博指定 ID...
uv run --frozen python -m media_platform.weibo.get_specified_ids --lt cookie
if %errorlevel% neq 0 (
    echo [错误] 微博 ID 提取任务失败，终止后续操作。
    exit /b %errorlevel%
)

echo.
echo [2/2] 正在运行微博详情爬虫...
uv run --frozen main.py --platform wb --type detail --lt cookie --save_data_option sqlite
if %errorlevel% neq 0 (
    echo [错误] 微博详情爬虫执行失败。
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo [%date% %time%] 任务全部完成。
echo ============================================================
