# -*- coding: utf-8 -*-
# Copyright (c) 2025 JJ_Superman
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/cwj007/JNU-OPORC/tree/master
# GitHub: https://github.com/cwj007
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

# -*- coding: utf-8 -*-
# @Author  : JJ_Superman
# @Time    : 2023/12/23 15:41
# @Desc    : Weibo crawler main workflow code

import asyncio
import os
import re
import glob
import time
from asyncio import Task
from typing import Dict, List, Optional, Tuple

try:
    import msvcrt
except ImportError:
    msvcrt = None
from urllib.parse import unquote

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)

import config
from base.base_crawler import AbstractCrawler
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import weibo as weibo_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from var import crawler_type_var, source_keyword_var, top_id_var

from .client import WeiboClient
from .exception import DataFetchError
from .field import SearchType
from .help import filter_search_result_card
from .login import WeiboLogin


class WeiboCrawler(AbstractCrawler):
    context_page: Page  # Playwright 页面对象
    wb_client: WeiboClient  # 微博 API 客户端对象
    browser_context: BrowserContext  # 浏览器上下文对象
    cdp_manager: Optional[CDPBrowserManager]  # CDP 模式管理器对象

    def __init__(self):
        self.index_url = "https://www.weibo.com"  # 微博 PC 端主页 URL
        self.mobile_index_url = "https://m.weibo.cn"  # 微博移动端主页 URL
        self.user_agent = utils.get_user_agent()  # 获取随机的 PC 端 User-Agent
        self.mobile_user_agent = utils.get_mobile_user_agent()  # 获取随机的移动端 User-Agent
        self.cdp_manager = None  # 初始化 CDP 管理器为空
        self.ip_proxy_pool = None  # 初始化代理 IP 池为空，用于自动刷新代理

    async def start(self):
        playwright_proxy_format, httpx_proxy_format = None, None  # 初始化代理格式变量
        if config.ENABLE_IP_PROXY:  # 如果配置文件中开启了 IP 代理
            self.ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=config.ENABLE_VALIDATE_IP)  # 创建并初始化代理池
            ip_proxy_info: IpInfoModel = await self.ip_proxy_pool.get_proxy()  # 从代理池获取一个代理 IP
            playwright_proxy_format, httpx_proxy_format = utils.format_proxy_info(ip_proxy_info)  # 格式化代理信息供不同库使用

        async with async_playwright() as playwright:  # 启动 playwright 上下文管理器
            # 根据配置选择启动模式
            if config.ENABLE_CDP_MODE:  # 如果开启了 CDP 模式（通过浏览器远程控制）
                utils.logger.info("[WeiboCrawler] Launching browser with CDP mode")  # 记录日志：以 CDP 模式启动
                self.browser_context = await self.launch_browser_with_cdp(  # 调用 CDP 模式启动浏览器的函数
                    playwright,
                    playwright_proxy_format,
                    self.mobile_user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:  # 否则使用标准启动模式
                utils.logger.info("[WeiboCrawler] Launching browser with standard mode")  # 记录日志：以标准模式启动
                # 启动浏览器上下文
                chromium = playwright.chromium  # 获取 chromium 浏览器类型
                self.browser_context = await self.launch_browser(chromium, None, self.mobile_user_agent, headless=config.HEADLESS)  # 启动浏览器

                # stealth.min.js 是用于防止网站检测到爬虫的 JS 脚本
                await self.browser_context.add_init_script(path="libs/stealth.min.js")  # 在页面初始化前注入反检测脚本


            self.context_page = await self.browser_context.new_page()  # 在浏览器上下文中创建一个新页面
            
            # 优先访问移动端主页，PC 端主页 (www.weibo.com) 经常会由于反爬导致 ERR_CONNECTION_CLOSED
            async def goto_with_retry(url, max_retries=3):
                for i in range(max_retries):
                    try:
                        utils.logger.info(f"[WeiboCrawler.start] Visiting {url} (attempt {i+1}/{max_retries}) ...")
                        await self.context_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        return True
                    except Exception as e:
                        utils.logger.warning(f"[WeiboCrawler.start] Visit {url} failed: {e}")
                        if i < max_retries - 1:
                            await asyncio.sleep(2)
                return False

            if not await goto_with_retry(self.mobile_index_url):
                utils.logger.warning(f"[WeiboCrawler.start] Visiting mobile index failed after retries, trying PC index as fallback...")
                if not await goto_with_retry(self.index_url):
                    utils.logger.error(f"[WeiboCrawler.start] Both mobile and PC index failed after retries.")
                    # 如果都失败了，不一定要退出，后面 login 逻辑还会尝试
            
            await asyncio.sleep(2)  # 等待 2 秒，让页面加载


            # 创建用于与微博网站交互的客户端
            self.wb_client = await self.create_weibo_client(httpx_proxy_format)  # 初始化微博 API 请求客户端
            
            # 如果配置了多 Cookie，初始化第一个 Cookie
            if config.WEIBO_COOKIES_LIST and config.WEIBO_COOKIES_LIST[0].get("value"):
                utils.logger.info(f"[WeiboCrawler.start] Use multi-cookie mode, init with ID: {config.WEIBO_COOKIES_LIST[0].get('id')}")
                await self.wb_client.switch_cookie() # 借用 switch_cookie 逻辑进行初始化

            if not await self.wb_client.pong():  # 如果客户端检查登录状态失败（pong 失败）
                login_obj = WeiboLogin(  # 创建微博登录处理对象
                    login_type=config.LOGIN_TYPE,  # 登录类型（二维码、手机号或 Cookie）
                    login_phone="",  # 手机号（如果需要）
                    browser_context=self.browser_context,  # 传入浏览器上下文
                    context_page=self.context_page,  # 传入当前页面对象
                    cookie_str=config.COOKIES,  # 传入配置的 Cookie
                )
                await login_obj.begin()  # 开始执行登录流程

                # 登录成功后，跳转到移动端主页并更新移动端平台的 Cookie
                utils.logger.info("[WeiboCrawler.start] redirect weibo mobile homepage and update cookies on mobile platform")  # 记录日志
                await self.context_page.goto(self.mobile_index_url)  # 跳转到微博移动端
                await self.context_page.wait_for_load_state("networkidle")
                await asyncio.sleep(5)  # 等待 5 秒以确保 Cookie 完全写入
                # 仅获取移动端 Cookie，避免 PC 端和移动端 Cookie 混淆
                await self.wb_client.update_cookies(  # 更新客户端的 Cookie
                    browser_context=self.browser_context,
                    urls=[self.mobile_index_url]
                )
                
                # 再次确认登录状态
                if not await self.wb_client.pong():
                    utils.logger.warning("[WeiboCrawler.start] Login verify failed after redirect, but continuing anyway...")

            crawler_type_var.set(config.CRAWLER_TYPE)  # 设置当前爬取的类型变量（全局 ContextVar）
            if config.CRAWLER_TYPE == "search":  # 如果爬取类型是“搜索”
                # 搜索微博并获取其评论信息
                await self.search()  # 执行搜索爬取流程
            elif config.CRAWLER_TYPE == "detail":  # 如果爬取类型是“详情”
                # 获取指定微博帖子的信息和评论
                await self.get_specified_notes()  # 执行指定帖子爬取流程
            elif config.CRAWLER_TYPE == "creator":  # 如果爬取类型是“创作者”
                # 获取创作者信息及其发布的帖子和评论
                await self.get_creators_and_notes()  # 执行创作者爬取流程
            else:
                pass  # 未知类型，暂不处理
            utils.logger.info("[WeiboCrawler.start] Weibo Crawler finished ...")  # 记录日志：微博爬虫执行结束

    async def search(self):
        """
        根据关键词搜索微博帖子
        :return:
        """
        utils.logger.info("[WeiboCrawler.search] Begin search weibo keywords")  # 记录日志：开始关键词搜索
        weibo_limit_count = 10  # 微博搜索接口每页固定的数量限制
        # 不再强制修改用户的配置，尊重用户设置的最大爬取量
        start_page = config.START_PAGE  # 获取配置的起始页码

        # 根据配置设置微博搜索类型（默认、实时、热门、视频等）
        if config.WEIBO_SEARCH_TYPE == "default":
            search_type = SearchType.DEFAULT  # 默认搜索
        elif config.WEIBO_SEARCH_TYPE == "real_time":
            search_type = SearchType.REAL_TIME  # 实时搜索
        elif config.WEIBO_SEARCH_TYPE == "popular":
            search_type = SearchType.POPULAR  # 热门搜索
        elif config.WEIBO_SEARCH_TYPE == "video":
            search_type = SearchType.VIDEO  # 视频搜索
        else:
            utils.logger.error(f"[WeiboCrawler.search] Invalid WEIBO_SEARCH_TYPE: {config.WEIBO_SEARCH_TYPE}")  # 错误日志：无效的搜索类型
            return

        for keyword in config.KEYWORDS.split(","):  # 遍历配置中的每个关键词
            source_keyword_var.set(keyword)  # 设置当前关键词变量
            utils.logger.info(f"[WeiboCrawler.search] Current search keyword: {keyword}")  # 记录日志：当前搜索的关键词
            page = 1  # 从第 1 页开始迭代
            # 记录当前关键词已爬取的数量
            current_keyword_notes_count = 0
            while current_keyword_notes_count < config.CRAWLER_MAX_NOTES_COUNT:  # 只要还没达到最大爬取数量
                if page < start_page:  # 如果当前页小于起始页
                    utils.logger.info(f"[WeiboCrawler.search] Skip page: {page}")  # 记录日志：跳过页码
                    page += 1  # 页码加 1
                    continue
                utils.logger.info(f"[WeiboCrawler.search] search weibo keyword: {keyword}, page: {page}")  # 记录日志：正在搜索
                search_res = await self.wb_client.get_note_by_keyword(keyword=keyword, page=page, search_type=search_type)  # 调用 API 获取搜索结果
                note_id_list: List[str] = []  # 初始化帖子 ID 列表
                note_list = filter_search_result_card(search_res.get("cards"))  # 过滤并提取搜索结果中的卡片数据
                # 如果开启了全文获取，则批量获取帖子的完整正文
                remaining_count = config.CRAWLER_MAX_NOTES_COUNT - current_keyword_notes_count
                note_list = await self.batch_get_notes_full_text(note_list, max_count=remaining_count)  # 批量处理全文
                for note_item in note_list:  # 遍历帖子列表
                    if note_item:
                        mblog: Dict = note_item.get("mblog")  # 获取 mblog 对象（核心微博数据）
                        if mblog:
                            note_id = mblog.get("bid") or mblog.get("id")
                            note_id_list.append(note_id)  # 将帖子 ID 添加到列表

                            # 检查帖子是否已存在
                            if await weibo_store.check_content_exists(note_id):
                                utils.logger.info(f"[WeiboCrawler.search] weibo note id:{note_id} already exists, skip writing and image download ...")
                            else:
                                await weibo_store.update_weibo_note(note_item)  # 更新/保存微博帖子到存储
                                await self.get_note_images(mblog)  # 获取并保存帖子中的图片
                            
                            current_keyword_notes_count += 1
                            if current_keyword_notes_count >= config.CRAWLER_MAX_NOTES_COUNT:
                                utils.logger.info(f"[WeiboCrawler.search] Reached max notes count: {config.CRAWLER_MAX_NOTES_COUNT}")
                                break

                if current_keyword_notes_count >= config.CRAWLER_MAX_NOTES_COUNT:
                    await self.batch_get_notes_comments(note_id_list)
                    break

                page += 1  # 翻页

                # 翻页后的休眠，防止请求过快被封
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)  # 休眠
                utils.logger.info(f"[WeiboCrawler.search] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after page {page-1}")  # 记录日志

                await self.batch_get_notes_comments(note_id_list)  # 批量获取本页所有帖子的评论

    async def _get_latest_specified_ids(self) -> Dict[str, List[str]]:
        """从 source/weibo/specified_ids 目录加载最新提取的 ID 文件"""
        # 使用相对于项目根目录的路径
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # 修正：MediaCrawler 目录下可能还有一个 MediaCrawler 子目录，或者 source 在根目录
        # 根据 LS 结果，source 在 E:\JNU-OPORC\MediaCrawler\source
        base_path = os.path.join(project_root, "source", "weibo", "specified_ids")
        
        # 兜底检查：如果 project_root/source 不存在，尝试 project_root/MediaCrawler/source
        if not os.path.exists(base_path):
            base_path = os.path.join(project_root, "MediaCrawler", "source", "weibo", "specified_ids")
            
        utils.logger.info(f"[WeiboCrawler._get_latest_specified_ids] Searching for ID files in: {base_path}")
        
        if not os.path.exists(base_path):
            utils.logger.warning(f"[WeiboCrawler._get_latest_specified_ids] Base path not found: {base_path}")
            return {}
        
        # 查找所有 .txt 文件
        import glob
        files = glob.glob(os.path.join(base_path, "**", "*.txt"), recursive=True)
        utils.logger.info(f"[WeiboCrawler._get_latest_specified_ids] Found {len(files)} potential ID files.")
        
        if not files:
            return {}
        
        # 按修改时间排序，取最新的
        latest_file = max(files, key=os.path.getmtime)
        utils.logger.info(f"[WeiboCrawler._get_latest_specified_ids] Loading latest ID file: {latest_file}")

        top_to_ids = {}
        current_top = "未分类"
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                for line in f:
                    content = line.strip()
                    if not content:
                        continue
                    
                    if content.startswith("Top URL: "):
                        current_top = content[9:].strip()
                        if current_top not in top_to_ids:
                            top_to_ids[current_top] = []
                    elif content.startswith("- "):
                        # 兼容 "  - ID" 和 "- ID"
                        id_val = content[2:].strip()
                        if id_val:
                            top_to_ids.setdefault(current_top, []).append(id_val)
            
            # 去重并清理空板块
            result = {k: list(dict.fromkeys(v)) for k, v in top_to_ids.items() if v}
            total_ids = sum(len(ids) for ids in result.values())
            utils.logger.info(f"[WeiboCrawler._get_latest_specified_ids] 成功加载了 {len(result)} 个板块，共 {total_ids} 个 ID")
            return result
        except Exception as e:
            utils.logger.error(f"[WeiboCrawler._get_latest_specified_ids] 读取文件出错: {e}")
            return {}

    async def _extract_ids_from_latest_top(self) -> Dict[str, List[str]]:
        """从 source/weibo/top 目录加载最新热门榜单并提取 ID"""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        base_path = os.path.join(project_root, "source", "weibo", "top")
        
        if not os.path.exists(base_path):
            base_path = os.path.join(project_root, "MediaCrawler", "source", "weibo", "top")
            
        utils.logger.info(f"[WeiboCrawler._extract_ids_from_latest_top] Searching for top files in: {base_path}")
        
        if not os.path.exists(base_path):
            utils.logger.warning(f"[WeiboCrawler._extract_ids_from_latest_top] Base path not found: {base_path}")
            return {}
        
        files = glob.glob(os.path.join(base_path, "**", "*.txt"), recursive=True)
        if not files:
            return {}
        
        latest_file = max(files, key=os.path.getmtime)
        utils.logger.info(f"[WeiboCrawler._extract_ids_from_latest_top] Parsing latest top file: {latest_file}")
        
        urls = []
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                for line in f:
                    content = line.strip()
                    if content.startswith("- [URL: `") and content.endswith("`]"):
                        url = content[9:-2].strip()
                        if url:
                            urls.append(url)
        except Exception as e:
            utils.logger.error(f"[WeiboCrawler._extract_ids_from_latest_top] Error reading top file: {e}")
            return {}

        if not urls:
            return {}

        # 如果需要从 top URL 提取 ID，我们需要启动一个临时的爬取流程
        # 但为了简单起见，我们可以提示用户先运行提取脚本
        utils.logger.warning("[WeiboCrawler] 发现热门榜单文件但尚未提取 ID，请先运行: uv run python -m media_platform.weibo.get_specified_ids")
        return {}

    @staticmethod
    async def async_input(prompt: str, timeout: float = 5.0) -> str:
        """带超时的非阻塞输入 (Windows 兼容)"""
        print(prompt, end='', flush=True)
        if msvcrt:
            start_time = time.time()
            input_str = ""
            while time.time() - start_time < timeout:
                if msvcrt.kbhit():
                    char = msvcrt.getwche()
                    if char in ('\r', '\n'):
                        print()
                        return input_str
                    elif char == '\b':  # 退格键
                        if len(input_str) > 0:
                            input_str = input_str[:-1]
                            # getwche 已经回显了退格，但通常需要清除字符
                            print(' \b', end='', flush=True)
                    else:
                        input_str += char
                await asyncio.sleep(0.05)
            print("\n[等待超时] 自动跳过")
            return ""
        else:
            # 非 Windows 系统退回到 thread 模式 (虽然会有阻塞残留，但目前环境是 Windows)
            try:
                return await asyncio.wait_for(asyncio.to_thread(input, ""), timeout=timeout)
            except asyncio.TimeoutError:
                return ""

    async def get_specified_notes(self):
        """
        获取指定 ID 的微博帖子信息（支持交互式选择和顺序爬取）
        :return:
        """
        all_info: List[Tuple[str, str]] = []  # [(note_id, top_id), ...]

        # 1. 优先获取命令行指定的 ID（存入 WEIBO_CREATOR_ID_LIST）
        if config.IS_CLI_SPECIFIED_ID:
            all_ids = list(config.WEIBO_CREATOR_ID_LIST)
            utils.logger.info(f"[WeiboCrawler.get_specified_notes] 使用命令行指定的 ID: {all_ids}")
            # 命令行指定的 ID 没有对应的 top_id，传空
            all_info = [(nid, "") for nid in all_ids]
        else:
            all_ids = []
            utils.logger.info("[WeiboCrawler.get_specified_notes] 未在命令行指定 ID，准备从已提取的文件加载...")
            
            # 获取解析后的 ID 字典 (由 get_specified_ids.py 预先提取)
            top_to_ids = await self._get_latest_specified_ids()
            
            # 如果没有提取好的 ID，尝试从最新的 top 文件提取 (或者提示用户)
            if not top_to_ids:
                top_to_ids = await self._extract_ids_from_latest_top()
            
            if top_to_ids:
                # 交互式选择板块
                print("\n" + "="*50)
                print("[微博爬虫] 发现以下已提取的板块：")
                sections = list(top_to_ids.keys())
                for i, url in enumerate(sections, 1):
                    keyword = "未知板块"
                    match = re.search(r'q=([^&]+)', url)
                    if match:
                        keyword = unquote(match.group(1))
                    ids_count = len(top_to_ids[url])
                    print(f"{i}. {keyword} (含 {ids_count} 个帖子)")
                    print(f"   目标url: [URL: `{url}`]")
                
                print("\n请输入板块编号选择爬取范围（例如: 1,3 或 1-5），直接回车表示爬取全部板块（5秒后自动跳过）：")
                choice = await self.async_input(">> ", timeout=5.0)
                
                target_sections = []
                if not choice.strip():
                    target_sections = sections
                else:
                    try:
                        if "-" in choice:
                            start, end = map(int, choice.split("-"))
                            target_sections = sections[start-1:end]
                        else:
                            indices = [int(i.strip()) for i in choice.split(",") if i.strip()]
                            target_sections = [sections[i-1] for i in indices if 0 < i <= len(sections)]
                    except Exception as e:
                        print(f"输入格式错误 ({e})，将爬取全部板块")
                        target_sections = sections
                
                # 汇总所选板块的所有 ID
                selected_info: List[Tuple[str, str]] = []  # [(note_id, top_id), ...]
                for section in target_sections:
                    # 提取 top_id (即 URL 中的 q 参数)
                    match = re.search(r'q=([^&]+)', section)
                    top_id = match.group(1) if match else section
                    for note_id in top_to_ids[section]:
                        selected_info.append((note_id, top_id))
                
                # 如果选择了板块，再次询问是否限制每个板块的帖子数
                if target_sections:
                    print(f"\n当前已选择 {len(target_sections)} 个板块。")
                    print(f"请输入每个板块爬取的帖子数量上限（当前最高阀值为5，如果要设置更高参数，请设置 weibo_config.TOP_URL_COUNT_LIMIT 变量），直接回车表示爬取该板块下全部帖子（5秒后自动跳过）：")
                    limit_choice = await self.async_input(">> ", timeout=5.0)
                    if limit_choice.strip():
                        try:
                            limit = int(limit_choice.strip())
                            # 重新过滤每个板块的 ID
                            all_info = []
                            for section in target_sections:
                                match = re.search(r'q=([^&]+)', section)
                                top_id = match.group(1) if match else section
                                for note_id in top_to_ids[section][:limit]:
                                    all_info.append((note_id, top_id))
                        except:
                            all_info = selected_info
                    else:
                        all_info = selected_info
                
                utils.logger.info(f"[WeiboCrawler.get_specified_notes] 已筛选出 {len(all_info)} 个帖子 ID 准备爬取。")
                print("="*50 + "\n")
            else:
                utils.logger.warning("[WeiboCrawler.get_specified_notes] 未能加载到任何已提取的 ID。")
                return
        
        if not all_info:
            utils.logger.warning("[WeiboCrawler.get_specified_notes] 没有待爬取的指定 ID")
            return

        utils.logger.info(f"[WeiboCrawler.get_specified_notes] 开始顺序爬取，总计 {len(all_info)} 个帖子")

        # 3. 顺序爬取：一个 ID 完成后再开始下一个
        for i, (note_id, top_id) in enumerate(all_info, 1):
            top_id_var.set(top_id)  # 设置当前帖子的 top_id
            utils.logger.info(f"[WeiboCrawler.get_specified_notes] 正在处理第 {i}/{len(all_info)} 个帖子: {note_id}, top_id: {top_id}")
            
            # 检查帖子是否已存在
            note_exists = await weibo_store.check_content_exists(note_id)
            
            # 获取帖子详情
            note_item = await self.get_note_info_task(note_id)
            if note_item:
                mblog = note_item.get("mblog", {})
                
                if not note_exists:
                    await weibo_store.update_weibo_note(note_item)
                    # 获取并保存帖子中的图片 (如果开启了该功能)
                    if config.ENABLE_GET_MEIDAS:
                        # 获取帖子中的图片 (mblog 中包含图片列表)
                        await self.get_note_images(mblog)
                else:
                    utils.logger.info(f"[WeiboCrawler.get_specified_notes] weibo note id:{note_id} already exists, skip writing and image download ...")
                
                # 始终获取该帖子的评论（除非配置关闭）
                if config.ENABLE_GET_COMMENTS:
                    await self.get_note_comments(note_id, note_item)
            
            # 每个 ID 处理完后的休眠，避免请求过快
            if i < len(all_ids):
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

    async def get_note_info_task(self, note_id: str, semaphore: Optional[asyncio.Semaphore] = None) -> Optional[Dict]:
        """
        获取单个微博帖子详情的任务
        :param note_id: 微博 ID
        :param semaphore: 信号量（可选）
        :return:
        """
        if semaphore:
            async with semaphore:
                return await self._get_note_info(note_id)
        return await self._get_note_info(note_id)

    async def _get_note_info(self, note_id: str) -> Optional[Dict]:
        try:
            result = await self.wb_client.get_note_info_by_id(note_id)
            # 请求详情后的休眠
            await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
            return result
        except DataFetchError as ex:
            utils.logger.error(f"[WeiboCrawler.get_note_info_task] Get note detail error: {ex}")
            return None
        except Exception as ex:
            utils.logger.error(f"[WeiboCrawler.get_note_info_task] note_id:{note_id}, err: {ex}")
            return None

    async def get_note_comments(self, note_id: str, note_item: Optional[Dict] = None, semaphore: Optional[asyncio.Semaphore] = None):
        """
        获取指定帖子的所有评论
        :param note_id: 微博 ID
        :param note_item: 已获取的帖子详情（可选，用于优化请求）
        :param semaphore: 信号量（可选）
        :return:
        """
        if semaphore:
            async with semaphore:
                await self._get_note_comments_impl(note_id, note_item)
        else:
            await self._get_note_comments_impl(note_id, note_item)

    async def _get_note_comments_impl(self, note_id: str, note_item: Optional[Dict] = None):
        try:
            # 如果没有传入详情，则请求详情以检查评论数
            if not note_item:
                note_item = await self.wb_client.get_note_info_by_id(note_id)
            
            if not note_item or not note_item.get("mblog"):
                utils.logger.warning(f"[WeiboCrawler.get_note_comments] note_id: {note_id} not found, skip comments")
                return

            mblog = note_item.get("mblog")
            comments_count = mblog.get("comments_count", 0)
            
            # 转换评论数为数值
            count_num = 0
            if isinstance(comments_count, str):
                if "万" in comments_count:
                    count_num = int(float(comments_count.replace("万", "")) * 10000)
                else:
                    count_num = int(comments_count)
            else:
                count_num = int(comments_count)

            if count_num <= 0:
                utils.logger.info(f"[WeiboCrawler.get_note_comments] 微博ID: {note_id} 当前文章没有评论")
                return

            # 优化：如果评论数小于等于配置的上限，直接爬取全部评论
            max_count = config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES
            actual_fetch_count = min(count_num, max_count)
            
            utils.logger.info(f"[WeiboCrawler.get_note_comments] 开始获取微博ID: {note_id} 的评论 (总数: {count_num}, 计划爬取: {actual_fetch_count}) ...")

            # 获取评论前的休眠
            await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

            # 创建一个包装回调函数，在保存评论后尝试抓取图片
            async def save_comments_with_images(note_id: str, comment_list: List[Dict]):
                # 检查评论是否已经存在，如果存在则跳过
                filtered_comment_list = []
                for comment in comment_list:
                    comment_id = str(comment.get("id"))
                    if await weibo_store.check_comment_exists(comment_id, note_id=note_id):
                        utils.logger.info(f"[WeiboCrawler.save_comments_with_images] Weibo comment id:{comment_id} already exists, skip save and image download ...")
                        continue
                    filtered_comment_list.append(comment)

                if not filtered_comment_list:
                    return

                # 保存评论数据
                await weibo_store.batch_update_weibo_note_comments(note_id, filtered_comment_list)
                
                # 如果开启了媒体抓取，则尝试下载评论中的图片
                if config.ENABLE_GET_MEIDAS:
                    save_option = config.SAVE_DATA_OPTION
                    for comment in filtered_comment_list:
                        # 提取图片列表：优先使用 pics (多图)，如果没有则使用 pic (单图)
                        comment_pics = comment.get("pics") or []
                        if not comment_pics and comment.get("pic"):
                            comment_pics = [comment.get("pic")]
                        
                        if not comment_pics:
                            continue

                        comment_id = str(comment.get("id"))
                        # 根据 SAVE_DATA_OPTION 动态生成存储路径: data/weibo/{save_option}/{note_id}/imgs/{comment_id}
                        save_path = f"data/weibo/{save_option}/{note_id}/imgs/{comment_id}"
                        for index, pic in enumerate(comment_pics, 1):
                            # 提取图片 URL，优先提取高清大图 URL (large)，其次是中间尺寸 (mw2000)
                            url = pic.get("large", {}).get("url") or pic.get("mw2000", {}).get("url") or pic.get("url")
                            
                            # 过滤无效 URL (如 &690 占位符)
                            if not url or "&690" in url:
                                continue
                                
                            pid = pic.get("pid") or f"{comment_id}_{index}"
                            
                            if url:
                                # 构造文件名：如果是单张图，直接使用 comment_id；如果是多张图，则从 comment_id_1 开始编号
                                save_name = comment_id if len(comment_pics) == 1 else f"{comment_id}_{index}"
                                
                                utils.logger.info(f"[WeiboCrawler.get_note_comments] 正在下载评论图片: {url}")
                                content = await self.wb_client.get_note_image(url)
                                if content:
                                    extension = url.split(".")[-1]
                                    await weibo_store.update_weibo_note_image(
                                        pid, content, extension, 
                                        save_path=save_path, 
                                        save_name=save_name
                                    )
                                # 下载后的休眠
                                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

            await self.wb_client.get_note_all_comments(
                note_id=note_id,
                crawl_interval=config.CRAWLER_MAX_SLEEP_SEC,
                callback=save_comments_with_images,
                max_count=max_count,
            )
        except DataFetchError as ex:
            utils.logger.error(f"[WeiboCrawler.get_note_comments] get note_id: {note_id} comment error: {ex}")
        except Exception as e:
            utils.logger.error(f"[WeiboCrawler.get_note_comments] may be been blocked, err:{e}")

    async def batch_get_notes_comments(self, note_id_list: List[str]):
        """
        批量获取微博帖子的评论
        :param note_id_list: 帖子 ID 列表
        :return:
        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(f"[WeiboCrawler.batch_get_notes_comments] Crawling comment mode is not enabled")
            return

        utils.logger.info(f"[WeiboCrawler.batch_get_notes_comments] Begin batch get notes comments, total: {len(note_id_list)}")
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for note_id in note_id_list:
            task = asyncio.create_task(self.get_note_comments(note_id, semaphore=semaphore))
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_note_images(self, mblog: Dict):
        """
        获取微博帖子中的图片
        :param mblog: 微博数据对象
        :return:
        """
        if not config.ENABLE_GET_MEIDAS:  # 如果未开启媒体文件抓取
            utils.logger.info(f"[WeiboCrawler.get_note_images] Crawling image mode is not enabled")  # 记录日志：未开启
            return

        # 微博图片可能存在于 pics 字段或被包含在长微博中
        pics: List = mblog.get("pics")  # 获取图片列表
        
        # 如果 pics 为空，尝试从 continue_tag 或其他地方查找图片（微博有时会把长图放在别处）
        # 但目前主要还是依赖 pics 字段
        if not pics:
            # 检查是否有单个图片 (有时 API 返回结构不同)
            pic_ids = mblog.get("pic_ids")
            pic_infos = mblog.get("pic_infos")
            if pic_infos and pic_ids:
                pics = [pic_infos[pid] for pid in pic_ids if pid in pic_infos]
        
        if not pics:  # 如果依然没有图片
            return
        
        # 获取 note_id 用于确定存储路径和文件名
        note_id = mblog.get("bid") or mblog.get("id")
        # 根据 SAVE_DATA_OPTION 动态生成存储路径: data/weibo/{save_option}/{note_id}/imgs/{note_id}
        save_option = config.SAVE_DATA_OPTION
        save_path = f"data/weibo/{save_option}/{note_id}/imgs/{note_id}"
        
        utils.logger.info(f"[WeiboCrawler.get_note_images] 发现帖子 {note_id} 有 {len(pics)} 张图片，准备下载...")

        for index, pic in enumerate(pics, 1):  # 遍历每张图片，使用 index 计数
            if isinstance(pic, str):  # 如果图片数据是字符串 URL
                url = pic
                pid = url.split("/")[-1].split(".")[0]  # 从 URL 提取图片 ID
            elif isinstance(pic, dict):  # 如果图片数据是字典对象
                # 优先提取高清大图 URL (large)，其次是原始图 (original)，最后是普通 URL
                url = pic.get("large", {}).get("url") or pic.get("mw2000", {}).get("url") or pic.get("url")
                pid = pic.get("pid", "")  # 提取图片 ID
            else:
                continue
            
            # 记录尝试下载的 URL
            utils.logger.info(f"[WeiboCrawler.get_note_images] 正在尝试下载第 {index} 张图片: {url}")
            
            # 过滤无效 URL (如 &690 占位符)
            if not url or "&690" in url:
                continue
            
            if not url:  # 如果 URL 为空
                continue
            
            # 构造文件名：如果是单张图，直接使用 note_id；如果是多张图，则从 note_id_1 开始编号
            save_name = note_id if len(pics) == 1 else f"{note_id}_{index}"
            
            content = await self.wb_client.get_note_image(url)  # 调用客户端下载图片内容
            if content is None:
                utils.logger.warning(f"[WeiboCrawler.get_note_images] 第 {index} 张图片下载失败: {url}")
                continue
                
            await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)  # 下载后的休眠
            
            extension_file_name = url.split(".")[-1]  # 提取文件后缀名
            await weibo_store.update_weibo_note_image(
                pid, content, extension_file_name, 
                save_path=save_path, 
                save_name=save_name
            )  # 保存图片到存储

    async def get_creators_and_notes(self) -> None:
        """
        获取创作者信息及其发布的微博和评论
        Returns:

        """
        utils.logger.info("[WeiboCrawler.get_creators_and_notes] Begin get weibo creators")  # 记录日志：开始获取创作者
        total_notes_count = 0
        for user_id in config.WEIBO_CREATOR_ID_LIST:  # 遍历配置的创作者 ID 列表
            remaining_count = config.CRAWLER_MAX_NOTES_COUNT - total_notes_count
            if remaining_count <= 0:
                break

            try:
                createor_info_res: Dict = await self.wb_client.get_creator_info_by_id(creator_id=user_id)  # 获取创作者详情
            except DataFetchError as e:
                utils.logger.error(f"[WeiboCrawler.get_creators_and_notes] Get creator info error: {e}, creator_id:{user_id}")
                continue

            if createor_info_res:
                createor_info: Dict = createor_info_res.get("userInfo", {})  # 提取用户信息
                utils.logger.info(f"[WeiboCrawler.get_creators_and_notes] creator info: {createor_info}")  # 记录日志
                if not createor_info:  # 如果获取用户信息失败
                    raise DataFetchError("Get creator info error")
                
                # Add logic to get cumulative counts by hovering
                try:
                    utils.logger.info(f"[WeiboCrawler.get_creators_and_notes] Navigating to creator profile for extra data: {user_id}")
                    profile_url = f"https://weibo.com/u/{user_id}"
                    await self.context_page.goto(profile_url)
                    await self.context_page.wait_for_load_state("networkidle")
                    
                    hover_xpath = '//*[@id="app"]/div[1]/div[2]/div[2]/main/div/div/div[2]/div[2]/div[2]/div[2]/a[3]'
                    try:
                        # Check if element exists and is visible
                        if await self.context_page.locator(hover_xpath).count() > 0:
                            await self.context_page.hover(hover_xpath)
                            await asyncio.sleep(1.5)  # Wait for tooltip
                            
                            reposts_xpath = '//*[@id="app"]/div[1]/div[2]/div[2]/main/div/div/div[2]/div[2]/div[2]/div[2]/a[3]/div/div[3]/span[2]'
                            comments_xpath = '//*[@id="app"]/div[1]/div[2]/div[2]/main/div/div/div[2]/div[2]/div[2]/div[2]/a[3]/div/div[4]/span[2]'
                            likes_xpath = '//*[@id="app"]/div[1]/div[2]/div[2]/main/div/div/div[2]/div[2]/div[2]/div[2]/a[3]/div/div[5]/span[2]'
                            
                            r_count = await self.context_page.locator(reposts_xpath).text_content()
                            c_count = await self.context_page.locator(comments_xpath).text_content()
                            l_count = await self.context_page.locator(likes_xpath).text_content()
                            
                            if r_count: createor_info['reposts_count'] = r_count.strip()
                            if c_count: createor_info['comments_count'] = c_count.strip()
                            if l_count: createor_info['likes_count'] = l_count.strip()
                            
                            utils.logger.info(f"[WeiboCrawler.get_creators_and_notes] Got extra counts: {r_count}, {c_count}, {l_count}")
                        else:
                            utils.logger.warning(f"[WeiboCrawler.get_creators_and_notes] Hover element not found for {user_id}")
                    except Exception as e:
                        utils.logger.warning(f"[WeiboCrawler.get_creators_and_notes] Error extracting extra counts: {e}")
                except Exception as e:
                    utils.logger.error(f"[WeiboCrawler.get_creators_and_notes] Failed to navigate for extra counts: {e}")

                await weibo_store.save_creator(user_id, user_info=createor_info)  # 保存创作者信息

                # 创建一个包装回调函数，在保存数据前先获取全文和图片
                async def save_notes_with_full_text(note_list: List[Dict]):
                    nonlocal total_notes_count
                    # 计算剩余需要抓取的数量
                    current_remaining = config.CRAWLER_MAX_NOTES_COUNT - total_notes_count
                    if current_remaining <= 0:
                        return

                    # 如果开启了全文抓取，则先批量处理
                    updated_note_list = await self.batch_get_notes_full_text(note_list, max_count=current_remaining)
                    for note_item in updated_note_list:
                        if total_notes_count >= config.CRAWLER_MAX_NOTES_COUNT:
                            break
                        
                        mblog = note_item.get("mblog", {})
                        note_id = mblog.get("bid") or mblog.get("id")
                        
                        # 检查帖子是否已存在
                        if await weibo_store.check_content_exists(note_id):
                            utils.logger.info(f"[WeiboCrawler.get_creators_and_notes] weibo note id:{note_id} already exists, skip writing and image download ...")
                        else:
                            await weibo_store.update_weibo_note(note_item)  # 保存帖子
                            if config.ENABLE_GET_MEIDAS:
                                await self.get_note_images(mblog)  # 保存图片
                            total_notes_count += 1

                # 获取该创作者的所有微博信息
                try:
                    all_notes_list = await self.wb_client.get_all_notes_by_creator_id(
                        creator_id=user_id,
                        container_id=f"107603{user_id}",  # 微博固定的个人主页容器 ID 前缀
                        crawl_interval=0,  # 内部会处理休眠
                        callback=save_notes_with_full_text,  # 分页抓取的回调
                    )
                except DataFetchError as e:
                    utils.logger.error(f"[WeiboCrawler.get_creators_and_notes] Get all notes error: {e}, creator_id:{user_id}")
                    all_notes_list = []

                note_ids = [note_item.get("mblog", {}).get("bid") or note_item.get("mblog", {}).get("id") for note_item in all_notes_list if note_item.get("mblog", {}).get("id")]  # 提取所有帖子 ID
                await self.batch_get_notes_comments(note_ids)  # 批量抓取这些帖子的评论

            else:
                utils.logger.error(f"[WeiboCrawler.get_creators_and_notes] get creator info error, creator_id:{user_id}")  # 错误日志

    async def create_weibo_client(self, httpx_proxy: Optional[str]) -> WeiboClient:
        """创建微博 API 客户端对象"""
        utils.logger.info("[WeiboCrawler.create_weibo_client] Begin create weibo API client ...")  # 记录日志
        cookie_str, cookie_dict = utils.convert_cookies(await self.browser_context.cookies(urls=[self.mobile_index_url]))  # 从浏览器上下文提取移动端 Cookie
        weibo_client_obj = WeiboClient(  # 实例化客户端
            proxy=httpx_proxy,  # 代理设置
            headers={
                "User-Agent": utils.get_mobile_user_agent(),  # 设置移动端 UA
                "Cookie": cookie_str,  # 设置 Cookie
                "Origin": "https://m.weibo.cn",  # 设置 Origin
                "Referer": "https://m.weibo.cn",  # 设置 Referer
                "Content-Type": "application/json;charset=UTF-8",  # 设置内容类型
            },
            playwright_page=self.context_page,  # 传入当前页面对象（用于处理人机校验）
            cookie_dict=cookie_dict,  # 传入 Cookie 字典
            proxy_ip_pool=self.ip_proxy_pool,  # 传入代理池（用于自动刷新）
        )
        return weibo_client_obj

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """启动浏览器并创建浏览器上下文"""
        utils.logger.info("[WeiboCrawler.launch_browser] Begin create browser context ...")  # 记录日志
        if config.SAVE_LOGIN_STATE:  # 如果开启了持久化登录状态
            user_id_suffix = f"_{config.VISUALIZED_USER_ID}" if config.VISUALIZED_USER_ID else ""
            user_data_dir = os.path.join(os.getcwd(), "browser_data", (config.USER_DATA_DIR % config.PLATFORM) + user_id_suffix)  # type: ignore  # 计算用户数据目录
            browser_context = await chromium.launch_persistent_context(  # 启动持久化上下文
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={
                    "width": 1920,
                    "height": 1080
                },
                user_agent=user_agent,
                channel="chrome",  # 使用系统的 Chrome 浏览器
            )
            return browser_context
        else:  # 否则启动普通（临时）浏览器
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy, channel="chrome")  # type: ignore
            browser_context = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=user_agent)  # 创建新上下文
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """
        使用 CDP 模式启动浏览器
        """
        try:
            self.cdp_manager = CDPBrowserManager()  # 实例化 CDP 管理器
            browser_context = await self.cdp_manager.launch_and_connect(  # 启动并连接浏览器
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            # 显示浏览器信息
            browser_info = await self.cdp_manager.get_browser_info()  # 获取浏览器详情
            utils.logger.info(f"[WeiboCrawler] CDP browser info: {browser_info}")  # 记录日志

            return browser_context

        except Exception as e:
            utils.logger.error(f"[WeiboCrawler] CDP mode startup failed, falling back to standard mode: {e}")  # 错误日志：回退到标准模式
            # 回退到标准模式
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)

    async def get_note_full_text(self, note_item: Dict) -> Dict:
        """
        获取微博帖子的全文内容
        如果帖子内容被截断（isLongText=True），则请求详情接口获取完整内容
        :param note_item: 帖子数据，包含 mblog 字段
        :return: 更新后的帖子数据
        """
        if not config.ENABLE_WEIBO_FULL_TEXT:  # 如果未开启全文获取功能
            return note_item

        mblog = note_item.get("mblog", {})  # 提取 mblog 数据
        if not mblog:
            return note_item

        # 检查是否是长文本
        is_long_text = mblog.get("isLongText", False)  # 提取是否长文本标志
        if not is_long_text:  # 如果不是长文本，直接返回
            return note_item

        note_id = mblog.get("id")  # 提取微博 ID
        if not note_id:
            return note_item

        try:
            utils.logger.info(f"[WeiboCrawler.get_note_full_text] Fetching full text for note: {note_id}")  # 记录日志：正在获取全文
            full_note = await self.wb_client.get_note_info_by_id(note_id)  # 请求详情接口获取全文
            if full_note and full_note.get("mblog"):  # 如果成功获取到详情
                # 用完整内容替换原始的截断内容
                note_item["mblog"] = full_note["mblog"]
                utils.logger.info(f"[WeiboCrawler.get_note_full_text] Successfully fetched full text for note: {note_id}")  # 记录日志

            # 请求后的休眠，防止触发频率限制
            await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
        except DataFetchError as ex:
            utils.logger.error(f"[WeiboCrawler.get_note_full_text] Failed to fetch full text for note {note_id}: {ex}")  # 记录错误日志
        except Exception as ex:
            utils.logger.error(f"[WeiboCrawler.get_note_full_text] Unexpected error for note {note_id}: {ex}")  # 记录意外异常

        return note_item

    async def batch_get_notes_full_text(self, note_list: List[Dict], max_count: int = 999) -> List[Dict]:
        """
        批量获取微博帖子的全文内容
        :param note_list: 帖子列表
        :param max_count: 最大获取数量
        :return: 更新后的帖子列表
        """
        if not config.ENABLE_WEIBO_FULL_TEXT:
            return note_list

        result = []
        for i, note_item in enumerate(note_list):
            if i >= max_count:
                result.append(note_item)
                continue
            updated_note = await self.get_note_full_text(note_item)
            result.append(updated_note)
        return result

    async def close(self):
        """Close browser context"""
        # Special handling if using CDP mode
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[WeiboCrawler.close] Browser context closed ...")
