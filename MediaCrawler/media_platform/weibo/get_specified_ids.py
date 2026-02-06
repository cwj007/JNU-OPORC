# -*- coding: utf-8 -*-
import asyncio
import os
import re
import pathlib
from typing import List, Optional
from urllib.parse import unquote

from playwright.async_api import async_playwright

import config
from .core import WeiboCrawler
from tools import utils

class WeiboTopIDExtractor(WeiboCrawler):
    def __init__(self):
        super().__init__()
        self.base_source_dir = r"e:\JNU-OPORC\MediaCrawler\source\weibo\top"
        self.target_base_dir = r"e:\JNU-OPORC\MediaCrawler\source\weibo\specified_ids"

    def get_latest_top_file_info(self):
        """获取最新的 top URL 文件信息"""
        if not os.path.exists(self.base_source_dir):
            utils.logger.warning(f"[WeiboTopIDExtractor] 基础目录不存在: {self.base_source_dir}")
            return None, None, None
        
        # 1. 获取所有日期目录 (YYYYMMDD 格式)
        date_dirs = [d for d in os.listdir(self.base_source_dir) 
                     if os.path.isdir(os.path.join(self.base_source_dir, d)) and re.match(r'\d{8}', d)]
        
        if not date_dirs:
            utils.logger.warning(f"[WeiboTopIDExtractor] 在 {self.base_source_dir} 下未找到有效的日期目录")
            return None, None, None
        
        # 按日期排序，取最新的
        date_dirs.sort()
        latest_date_dir = date_dirs[-1]
        full_date_path = os.path.join(self.base_source_dir, latest_date_dir)
        
        # 2. 在该目录下查找最新的 .txt 文件 (HH时MM分.txt 格式)
        time_files = [f for f in os.listdir(full_date_path) if f.endswith(".txt")]
        if not time_files:
            utils.logger.warning(f"[WeiboTopIDExtractor] 在 {full_date_path} 下未找到 .txt 文件")
            return None, None, None
            
        # 按文件名排序，取最新的
        time_files.sort()
        latest_time_file = time_files[-1]
        
        latest_file_path = os.path.join(full_date_path, latest_time_file)
        
        utils.logger.info(f"[WeiboTopIDExtractor] 自动匹配到最新日期目录: {latest_date_dir}, 最新文件: {latest_time_file}")
        return latest_file_path, latest_date_dir, latest_time_file

    async def extract_ids(self):
        """执行提取流程"""
        file_path, date_str, time_file = self.get_latest_top_file_info()
        if not file_path:
            utils.logger.error("[WeiboTopIDExtractor] 未找到热门榜单 URL 文件。")
            return

        utils.logger.info(f"[WeiboTopIDExtractor] 正在从文件读取热门榜单 URL: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]

        if not urls:
            utils.logger.error("[WeiboTopIDExtractor] 文件中没有 URL。")
            return

        # 获取配置的数量限制
        from config import weibo_config
        count_limit = getattr(weibo_config, "TOP_URL_COUNT_LIMIT", 5)
        utils.logger.info(f"[WeiboTopIDExtractor] 每个榜单页面将获取前 {count_limit} 个帖子 ID")

        # 启动浏览器并登录
        async with async_playwright() as playwright:
            # 根据配置选择启动模式 (复用 config 逻辑)
            if config.ENABLE_CDP_MODE:
                from tools.cdp_browser import CDPBrowserManager
                self.cdp_manager = CDPBrowserManager()
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright, None, self.user_agent, headless=config.CDP_HEADLESS
                )
            else:
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium, None, self.user_agent, headless=config.HEADLESS
                )
            
            self.context_page = await self.browser_context.new_page()
            
            # 访问主页并处理登录
            await self.context_page.goto(self.index_url)
            
            # 创建客户端
            self.wb_client = await self.create_weibo_client(None)
            
            # 确保 Cookie 注入到浏览器 (无论是单 Cookie 还是多 Cookie)
            if config.LOGIN_TYPE == "cookie":
                if config.WEIBO_COOKIES_LIST:
                    # switch_cookie 会自动调用 _cookie_index + 1 (从 -1 变 0) 并注入到浏览器
                    await self.wb_client.switch_cookie()
                else:
                    # 单 Cookie 模式，手动调用注入
                    from .login import WeiboLogin
                    login_obj = WeiboLogin(
                        login_type=config.LOGIN_TYPE,
                        browser_context=self.browser_context,
                        context_page=self.context_page,
                        cookie_str=config.COOKIES,
                    )
                    await login_obj.login_by_cookies()
                
                # 注入后再次访问主页以刷新状态
                await self.context_page.goto(self.index_url)
                await asyncio.sleep(2)

            if not await self.wb_client.pong():
                from .login import WeiboLogin
                login_obj = WeiboLogin(
                    login_type=config.LOGIN_TYPE,
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                
                # 登录成功后，跳转到移动端主页并更新移动端平台的 Cookie
                await self.context_page.goto(self.mobile_index_url)
                await self.context_page.wait_for_load_state("networkidle")
                await asyncio.sleep(5)
                await self.wb_client.update_cookies(
                    browser_context=self.browser_context,
                    urls=[self.mobile_index_url]
                )
            
            # 存储结果的字典，格式为 {top_url: [id1, id2, ...]}
            top_to_ids = {}
            
            # --- 交互式选择板块 ---
            print("\n" + "="*50)
            print("[微博 ID 提取器] 发现以下热门榜单板块：")
            for i, url in enumerate(urls, 1):
                keyword = "未知板块"
                match = re.search(r'q=([^&]+)', url)
                if match:
                    keyword = unquote(match.group(1))
                print(f"{i}. {keyword}")
                print(f"   目标url: [URL: `{url}`]")
            
            print("\n请输入板块编号选择解析范围（例如: 1,3 或 1-5），直接回车表示解析全部板块（5秒后自动跳过）：")
            choice = await self.async_input(">> ", timeout=5.0)
            
            target_urls = []
            if not choice.strip():
                target_urls = urls
            else:
                try:
                    if "-" in choice:
                        start, end = map(int, choice.split("-"))
                        target_urls = urls[start-1:end]
                    else:
                        indices = [int(i.strip()) for i in choice.split(",") if i.strip()]
                        target_urls = [urls[i-1] for i in indices if 0 < i <= len(urls)]
                except Exception as e:
                    print(f"输入格式错误 ({e})，将解析全部板块")
                    target_urls = urls
            
            # 选择每个板块爬取的数量
            print(f"\n当前已选择 {len(target_urls)} 个板块。")
            print(f"请输入每个板块提取的帖子数量上限（当前默认 {count_limit}），直接回车表示使用默认值（5秒后自动跳过）：")
            limit_choice = await self.async_input(">> ", timeout=5.0)
            if limit_choice.strip():
                try:
                    count_limit = int(limit_choice.strip())
                    utils.logger.info(f"[WeiboTopIDExtractor] 用户设置提取数量上限为: {count_limit}")
                except:
                    utils.logger.warning(f"[WeiboTopIDExtractor] 输入无效，将使用配置文件默认值: {count_limit}")
            else:
                utils.logger.info(f"[WeiboTopIDExtractor] 使用配置文件默认提取数量上限: {count_limit}")
            
            print("="*50 + "\n")
            
            # 输出爬取进度概览
            total_expected = len(target_urls) * count_limit
            utils.logger.info(f"[WeiboTopIDExtractor] 开始顺序爬取，总计预计提取 {total_expected} 个帖子 (共 {len(target_urls)} 个板块，每板块 {count_limit} 个)")
            # ----------------------

            # 提取器选择器 (综合用户提供和实际观察)
            selectors = [
                "#pl_feedlist_index div.card-feed div.from a[target='_blank']",
                "div.card-feed div.from a[target='_blank']",
                "div.from a[target='_blank']",
                "div.card-feed div.content a[target='_blank']"
            ]

            # 存储结果的目录准备
            target_dir = os.path.join(self.target_base_dir, date_str)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            target_file = os.path.join(target_dir, time_file)

            for url in target_urls:
                # 提取关键词用于日志显示，但保持 URL 编码以确保链接可点击
                keyword = "未知板块"
                match = re.search(r'q=([^&]+)', url)
                if match:
                    keyword = unquote(match.group(1))
                utils.logger.info(f"[WeiboTopIDExtractor] 正在处理热门榜单: {keyword}")
                utils.logger.info(f"[WeiboTopIDExtractor] 目标url: [URL: `{url}`]")
                try:
                    await self.context_page.goto(url)
                    await self.context_page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2) 
                    
                    found_ids = []
                    for selector in selectors:
                        elements = await self.context_page.query_selector_all(selector)
                        if elements:
                            for el in elements:
                                if len(found_ids) >= count_limit:
                                    break
                                href = await el.get_attribute("href")
                                if href:
                                    # 兼容多种 URL 格式：
                                    # 1. https://weibo.com/1234567890/Lz5Fz5Fz
                                    # 2. https://weibo.com/status/Lz5Fz5Fz
                                    # 3. /1234567890/Lz5Fz5Fz
                                    match = re.search(r'weibo\.com/(?:\d+|status)/([A-Za-z0-9]+)', href)
                                    if not match:
                                        # 处理相对路径 /1234567890/Lz5Fz5Fz
                                        match = re.search(r'^/(?:\d+|status)/([A-Za-z0-9]+)', href)
                                    
                                    if match:
                                        mid = match.group(1)
                                        # 排除掉一些明显的非 mid 字符串（比如 'home', 'hot' 等，虽然正则已经限制了路径）
                                        if mid not in found_ids and len(mid) >= 8:
                                            found_ids.append(mid)
                            if found_ids:
                                break
                    
                    if found_ids:
                        top_to_ids[url] = found_ids
                        utils.logger.info(f"[WeiboTopIDExtractor] 从该榜单成功提取到 {len(found_ids)} 个 ID")
                        
                        # 每提取完一个板块即刻写入文件 (追加模式)
                        with open(target_file, "a", encoding="utf-8") as f:
                            f.write(f"Top URL: {url}\n")
                            for sid in found_ids:
                                f.write(f"  - {sid}\n")
                            f.write("\n")
                        utils.logger.info(f"[WeiboTopIDExtractor] 已将板块 [{keyword}] 的结果追加到: {target_file}")
                    else:
                        utils.logger.warning(f"[WeiboTopIDExtractor] 未能从该榜单提取到任何 ID")
                except Exception as e:
                    utils.logger.error(f"[WeiboTopIDExtractor] 处理 URL {url} 时出错: {e}")

            # 最终检查
            if not top_to_ids:
                utils.logger.warning("[WeiboTopIDExtractor] 本次运行未提取到任何 ID。")
            else:
                utils.logger.info(f"[WeiboTopIDExtractor] 所有板块处理完成，结果已保存至: {target_file}")

            await self.browser_context.close()

if __name__ == "__main__":
    from cmd_arg import arg

    async def main():
        # 解析命令行参数
        await arg.parse_cmd()
        
        extractor = WeiboTopIDExtractor()
        await extractor.extract_ids()

    asyncio.run(main())
