@echo off
setlocal enabledelayedexpansion

:: Set UTF-8 code page
chcp 65001 >nul

echo ============================================================
echo [1/2] Running TrendRadar...
echo ============================================================

cd /d "e:\JNU-OPORC\trendradar"
if %errorlevel% neq 0 (
    echo [ERROR] Directory not found: e:\JNU-OPORC\trendradar
    pause
    exit /b 1
)

:: Use uv run main.py (no ./ for Windows CMD)
uv run --frozen main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] TrendRadar execution failed.
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo [2/2] Running MediaCrawler (Weibo ID Extraction)...
echo ============================================================

cd /d "e:\JNU-OPORC\MediaCrawler"
if %errorlevel% neq 0 (
    echo [ERROR] Directory not found: e:\JNU-OPORC\MediaCrawler
    pause
    exit /b 1
)

:: Run as a module to handle imports correctly
uv run --frozen python -m media_platform.weibo.get_specified_ids --lt cookie
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] MediaCrawler execution failed.
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo SUCCESS: All tasks completed.
echo ============================================================
pause
