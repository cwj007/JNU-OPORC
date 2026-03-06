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
# @Time    : 2023/12/23 15:40
# @Desc    : Weibo crawler API request client

import asyncio
import copy
import json
import re
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union
from urllib.parse import parse_qs, unquote, urlencode

import httpx
from httpx import Response
from playwright.async_api import BrowserContext, Page
from tenacity import retry, stop_after_attempt, wait_fixed

import config
from proxy.proxy_mixin import ProxyRefreshMixin
from tools import utils

if TYPE_CHECKING:
    from proxy.proxy_ip_pool import ProxyIpPool

from .exception import CookieInvalidError, DataFetchError
from .field import SearchType


class WeiboClient(ProxyRefreshMixin):
    """
    微博爬虫 API 请求客户端类，继承自 ProxyRefreshMixin 以支持代理自动刷新
    """

    def __init__(
        self,
        timeout=60,  # 如果开启媒体爬取，微博图片需要更长的超时时间
        proxy=None,  # 代理设置
        *,
        headers: Dict[str, str],  # 请求头
        playwright_page: Page,  # Playwright 页面对象，用于处理验证码或更新 Cookie
        cookie_dict: Dict[str, str],  # Cookie 字典
        proxy_ip_pool: Optional["ProxyIpPool"] = None,  # 代理 IP 池对象
    ):
        self.proxy = proxy  # 设置代理
        self.timeout = timeout  # 设置超时时间
        self.headers = headers  # 设置请求头
        self._host = "https://m.weibo.cn"  # 微博移动端 API 主机地址
        self.playwright_page = playwright_page  # 保存页面对象
        self.cookie_dict = cookie_dict  # 保存 Cookie 字典
        self._image_agent_host = "https://i1.wp.com/"  # 用于绕过微博图片防盗链的代理主机
        self._cookie_index = -1  # 当前使用的 Cookie 索引
        # 初始化代理池（来自 ProxyRefreshMixin）
        self.init_proxy_pool(proxy_ip_pool)

    async def switch_cookie(self):
        """
        切换到下一个可用的 Cookie
        """
        if not config.WEIBO_COOKIES_LIST:
            return False

        if len(config.WEIBO_COOKIES_LIST) == 1 and self._cookie_index != -1:
            utils.logger.error("[WeiboClient.switch_cookie] Only one cookie configured and it failed. Please update your COOKIES in config.")
        
        self._cookie_index = (self._cookie_index + 1) % len(config.WEIBO_COOKIES_LIST)
        new_cookie_item = config.WEIBO_COOKIES_LIST[self._cookie_index]
        new_cookie_value = new_cookie_item.get("value")
        cookie_id = new_cookie_item.get("id")

        if not new_cookie_value:
            utils.logger.warning(f"[WeiboClient.switch_cookie] Cookie ID:{cookie_id} value is empty, trying next...")
            return await self.switch_cookie()

        utils.logger.info(f"[WeiboClient.switch_cookie] Switching to Cookie ID: {cookie_id}")
        self.headers["Cookie"] = new_cookie_value
        # 更新浏览器上下文中的 Cookie，确保一致性
        # 注意：这里需要将字符串转换为 playwright 格式
        cookie_list = []
        for pair in new_cookie_value.split(";"):
            if "=" in pair:
                key, val = pair.strip().split("=", 1)
                for domain in [".weibo.cn", ".weibo.com"]:
                    cookie_list.append({"name": key, "value": val, "domain": domain, "path": "/"})
        
        await self.playwright_page.context.clear_cookies()
        await self.playwright_page.context.add_cookies(cookie_list)
        return True

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(3), reraise=True)
    async def request(self, method, url, **kwargs) -> Union[Response, Dict]:
        """
        发送 HTTP 请求的通用方法，包含自动重试逻辑
        :param method: 请求方法 (GET, POST 等)
        :param url: 请求 URL
        :param kwargs: 其他请求参数
        :return: 响应对象或解析后的 JSON 字典
        """
        # 在每次请求前检查代理是否过期
        await self._refresh_proxy_if_expired()

        enable_return_response = kwargs.pop("return_response", False)  # 是否直接返回原始响应对象
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            # 使用 httpx 发送异步请求
            response = await client.request(method, url, timeout=self.timeout, **kwargs)

        # 统一处理常见的封禁或重定向状态码
        if response.status_code in [403, 418, 302] or (response.status_code == 200 and not response.text.strip()):
            utils.logger.warning(f"[WeiboClient.request] Possible block or empty response, status code: {response.status_code}")
            
            # 尝试切换 Cookie
            if await self.switch_cookie():
                raise CookieInvalidError("Cookie may be blocked, switched to next one")
            
            # 如果没有更多 Cookie 可切换，尝试在浏览器中访问主页以刷新状态
            if self.playwright_page:
                utils.logger.info(f"[WeiboClient.request] Trying to refresh session by visiting {self._host}")
                await self.playwright_page.goto(self._host)
                await asyncio.sleep(2)
                await self.update_cookies(browser_context=self.playwright_page.context)
            
            if response.status_code == 302:
                utils.logger.error("[WeiboClient.request] 302 Redirect detected (to login page).")
            
            if not response.text.strip():
                raise DataFetchError(f"get empty response, code: {response.status_code}")
            
            raise DataFetchError(f"get response code error: {response.status_code}")

        if enable_return_response:
            return response

        try:
            data: Dict = response.json()  # 尝试解析 JSON 响应
        except json.decoder.JSONDecodeError:
            utils.logger.error(f"[WeiboClient.request] request {method}:{url} json decode err code: {response.status_code} res:{response.text[:100]}...")
            raise DataFetchError(f"json decode error, code: {response.status_code}")

        ok_code = data.get("ok")  # 微博 API 通常使用 ok 字段表示状态
        if ok_code == -100 and "captcha" in data.get("url", ""):
             utils.logger.warning(f"[WeiboClient.request] Captcha detected, opening browser to solve...")
             captcha_url = data.get("url")
             if self.playwright_page:
                 await self.playwright_page.goto(captcha_url)
                 utils.logger.info("[WeiboClient.request] Please solve the captcha in the browser window within 60 seconds...")
                 try:
                     # Wait for the user to solve the captcha and be redirected back
                     # The backUrl usually leads to the API response which is JSON text in browser
                     # So we just wait for the URL to change from the captcha URL
                     await self.playwright_page.wait_for_url(lambda u: "captcha" not in u, timeout=60000)
                     utils.logger.info("[WeiboClient.request] Captcha seems solved. Updating cookies and retrying...")
                     
                     # Sync cookies from browser to client
                     await self.update_cookies(browser_context=self.playwright_page.context)
                     
                     # Retry the request immediately
                     return await self.request(method, url, **kwargs)
                     
                 except Exception as e:
                     utils.logger.error(f"[WeiboClient.request] Failed to solve captcha or timeout: {e}")
             else:
                 utils.logger.error("[WeiboClient.request] Captcha detected but no browser page available to solve it.")

        if ok_code == 0:  # 响应错误
            msg = data.get("msg", "")
            if "登录" in msg or "login" in msg.lower() or "未登录" in msg:
                utils.logger.warning(f"[WeiboClient.request] Cookie invalid detected: {msg}")
                if await self.switch_cookie():
                    raise CookieInvalidError(f"Cookie invalid: {msg}, switched to next one")
            
            utils.logger.error(f"[WeiboClient.request] request {method}:{url} err, res:{data}")
            raise DataFetchError(data.get("msg", "response error"))
        elif ok_code != 1:  # 未知错误
            utils.logger.error(f"[WeiboClient.request] request {method}:{url} err, res:{data}")
            raise DataFetchError(data.get("msg", "unknown error"))
        else:  # 响应正确
            return data.get("data", {})  # 返回核心数据部分

    async def get(self, uri: str, params=None, headers=None, **kwargs) -> Union[Response, Dict]:
        """
        发送 GET 请求的快捷方法
        :param uri: 请求路径
        :param params: 查询参数字典
        :param headers: 自定义请求头
        :return: 响应内容
        """
        final_uri = uri
        if isinstance(params, dict):
            # 将参数字典编码并拼接到 URI
            final_uri = (f"{uri}?"
                         f"{urlencode(params)}")

        if headers is None:
            headers = self.headers
        return await self.request(method="GET", url=f"{self._host}{final_uri}", headers=headers, **kwargs)

    async def post(self, uri: str, data: dict) -> Dict:
        """
        发送 POST 请求的快捷方法
        :param uri: 请求路径
        :param data: 提交的数据字典
        :return: 响应内容
        """
        # 将数据转换为 JSON 字符串格式
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return await self.request(method="POST", url=f"{self._host}{uri}", data=json_str, headers=self.headers)

    async def pong(self) -> bool:
        """
        检查登录状态是否有效
        :return: 登录有效返回 True，否则返回 False
        """
        utils.logger.info("[WeiboClient.pong] Begin pong weibo...")
        # 如果是 cookie 登录，强制返回 True 信任用户提供的 Cookie
        if config.LOGIN_TYPE == "cookie":
            return True
            
        # 否则通过请求一个需要登录的接口来检查状态
        try:
            uri = "/api/config"
            # 直接调用 request 获取完整响应，因为 /api/config 可能不遵循 data 包装规范
            res = await self.request(method="GET", url=f"{self._host}{uri}", headers=self.headers)
            # 如果 res 是字典（说明 ok=1 且返回了 data 部分）
            if isinstance(res, dict) and res.get("login"):
                return True
            
            # 兼容处理：如果 get() 返回了空字典，或者我们需要检查外层的 login 字段
            # 我们可以直接请求并解析
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                response = await client.request("GET", f"{self._host}{uri}", headers=self.headers, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    # 检查 data.login 或 直接的 login
                    if data.get("login") or (data.get("data") and data.get("data").get("login")):
                        return True
        except Exception as e:
            utils.logger.error(f"[WeiboClient.pong] Pong weibo failed: {e}")
            
        return False

    async def update_cookies(self, browser_context: BrowserContext, urls: Optional[List[str]] = None):
        """
        从浏览器上下文中更新 Cookie
        :param browser_context: 浏览器上下文对象
        :param urls: 可选的 URL 列表，用于过滤特定域名的 Cookie
        """
        if urls:
            cookies = await browser_context.cookies(urls=urls)  # 获取指定 URL 的 Cookie
            utils.logger.info(f"[WeiboClient.update_cookies] Updating cookies for specific URLs: {urls}")
        else:
            cookies = await browser_context.cookies()  # 获取所有 Cookie
            utils.logger.info("[WeiboClient.update_cookies] Updating all cookies")

        cookie_str, cookie_dict = utils.convert_cookies(cookies)  # 将 Playwright Cookie 转换为字符串和字典格式
        self.headers["Cookie"] = cookie_str  # 更新请求头中的 Cookie
        self.cookie_dict = cookie_dict  # 更新本地 Cookie 字典
        utils.logger.info(f"[WeiboClient.update_cookies] Cookie updated successfully, total: {len(cookie_dict)} cookies")

    async def get_note_by_keyword(
        self,
        keyword: str,
        page: int = 1,
        search_type: SearchType = SearchType.DEFAULT,
    ) -> Dict:
        """
        根据关键词搜索帖子
        :param keyword: 微博搜索关键词
        :param page: 分页参数，当前页码
        :param search_type: 搜索类型，见 weibo/field.py 中的 SearchType 枚举
        :return: 搜索结果数据
        """
        uri = "/api/container/getIndex"
        containerid = f"100103type={search_type.value}&q={keyword}"  # 构建搜索容器 ID
        params = {
            "containerid": containerid,
            "page_type": "searchall",
            "page": page,
        }
        return await self.get(uri, params)

    async def get_note_comments(self, mid_id: str, max_id: int, max_id_type: int = 0) -> Dict:
        """
        获取帖子评论
        :param mid_id: 微博 ID
        :param max_id: 分页标识 ID
        :param max_id_type: 分页标识 ID 类型
        :return: 评论数据
        """
        uri = "/comments/hotflow"
        params = {
            "id": mid_id,
            "mid": mid_id,
            "max_id_type": max_id_type,
        }
        if max_id > 0:
            params.update({"max_id": max_id})
        referer_url = f"https://m.weibo.cn/detail/{mid_id}"  # 构建引用页 URL
        headers = copy.copy(self.headers)
        headers["Referer"] = referer_url  # 评论接口通常需要 Referer

        return await self.get(uri, params, headers=headers)

    async def get_note_all_comments(
        self,
        note_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ):
        """
        获取帖子所有评论，包括子评论
        :param note_id: 帖子 ID
        :param crawl_interval: 爬取间隔时间
        :param callback: 每页数据获取后的回调函数
        :param max_count: 最大获取评论数量
        :return: 评论列表
        """
        result = []
        is_end = False
        max_id = -1
        max_id_type = 0
        while not is_end and len(result) < max_count:
            comments_res = await self.get_note_comments(note_id, max_id, max_id_type)
            max_id: int = comments_res.get("max_id")  # 获取下一页的 ID
            max_id_type: int = comments_res.get("max_id_type")
            comment_list: List[Dict] = comments_res.get("data", [])  # 获取当前页评论列表
            is_end = max_id == 0  # 如果 max_id 为 0，表示没有更多评论
            if len(result) + len(comment_list) > max_count:
                comment_list = comment_list[:max_count - len(result)]  # 截断超过最大数量的部分
            if callback:  # 如果存在回调函数，则执行
                await callback(note_id, comment_list)
            await asyncio.sleep(crawl_interval)
            result.extend(comment_list)
            # 获取评论下的所有子评论
            sub_comment_result = await self.get_comments_all_sub_comments(note_id, comment_list, callback)
            result.extend(sub_comment_result)
        return result

    @staticmethod
    async def get_comments_all_sub_comments(
        note_id: str,
        comment_list: List[Dict],
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """
        获取评论列表中的所有子评论
        :param note_id: 帖子 ID
        :param comment_list: 评论列表
        :param callback: 回调函数
        :return: 子评论列表
        """
        if not config.ENABLE_GET_SUB_COMMENTS:  # 如果未开启爬取子评论功能
            utils.logger.info(f"[WeiboClient.get_comments_all_sub_comments] Crawling sub_comment mode is not enabled")
            return []

        res_sub_comments = []
        for comment in comment_list:
            sub_comments = comment.get("comments")  # 尝试从主评论中获取直接包含的子评论
            if sub_comments and isinstance(sub_comments, list):
                await callback(note_id, sub_comments)
                res_sub_comments.extend(sub_comments)
        return res_sub_comments

    async def get_note_info_by_id(self, note_id: str) -> Dict:
        """
        根据帖子 ID 获取帖子详情
        :param note_id: 帖子 ID
        :return: 帖子详情数据
        """
        url = f"/detail/{note_id}"
        # 使用 self.request 以支持重试和自动更新 Cookie
        # 内部已经处理了 status_code != 200 和空响应的情况
        response_text = await self.request(method="GET", url=f"{self._host}{url}", headers=self.headers, return_response=True)
        
        # 使用正则从页面 HTML 中提取渲染数据
        match = re.search(r'var \$render_data = (\[.*?\])\[0\]', response_text.text, re.DOTALL)
        if match:
            try:
                render_data_json = match.group(1)
                render_data_dict = json.loads(render_data_json)
                note_detail = render_data_dict[0].get("status")  # 提取帖子状态信息
                note_item = {"mblog": note_detail}
                return note_item
            except (json.JSONDecodeError, IndexError, KeyError) as e:
                utils.logger.error(f"[WeiboClient.get_note_info_by_id] Parse $render_data failed: {e}")
                return dict()
        else:
            # 如果没找到渲染数据，可能是被重定向到了登录页或其他错误页
            utils.logger.warning(f"[WeiboClient.get_note_info_by_id] $render_data value not found for note_id: {note_id}")
            # 记录部分响应内容以便调试
            utils.logger.debug(f"[WeiboClient.get_note_info_by_id] Response preview: {response_text.text[:200]}...")
            return dict()

    async def get_note_image(self, image_url: str) -> bytes:
        """
        下载帖子图片
        :param image_url: 图片原始 URL
        :return: 图片二进制内容
        """
        # 移除协议部分 (http:// 或 https://)
        if "://" in image_url:
            clean_url = image_url.split("://", 1)[1]
        else:
            clean_url = image_url
            
        sub_url = clean_url.split("/")
        # 微博图片 URL 结构通常为: host/size/filename.jpg
        # 我们尝试将 size 部分替换为 large 以获取高清大图
        if len(sub_url) >= 3:
            sub_url[1] = "large"
        
        processed_url = "/".join(sub_url)
        
        # 微博图片有防盗链，需要通过代理访问，并拼接到 i1.wp.com 代理主机下
        final_uri = f"{self._image_agent_host}{processed_url}"
        
        utils.logger.info(f"[WeiboClient.get_note_image] 正在下载图片: {final_uri}")
        
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            try:
                # 尝试通过代理主机下载
                response = await client.request("GET", final_uri, timeout=self.timeout)
                if response.status_code == 200:
                    return response.content
                
                utils.logger.warning(f"[WeiboClient.get_note_image] 代理下载失败 (HTTP {response.status_code}): {final_uri}")
            except Exception as exc:
                utils.logger.warning(f"[WeiboClient.get_note_image] 代理下载发生错误: {exc}")
            
            # 如果代理失败或发生错误，尝试直接下载原始 URL
            try:
                utils.logger.info(f"[WeiboClient.get_note_image] 尝试直接下载原始 URL: {image_url}")
                headers = copy.copy(self.headers)
                headers["Referer"] = "https://weibo.com/"
                resp = await client.request("GET", image_url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.content
                
                utils.logger.error(f"[WeiboClient.get_note_image] 直接下载原始 URL 失败 (HTTP {resp.status_code}): {image_url}")
            except Exception as exc:
                utils.logger.error(f"[WeiboClient.get_note_image] 直接下载原始 URL 发生错误: {exc}")
                
            return None

    async def get_creator_container_info(self, creator_id: str) -> Dict:
        """
        获取博主的容器 ID，容器信息代表了真实的 API 请求路径
            fid_container_id: 博主详情 API 的容器 ID
            lfid_container_id: 博主帖子列表 API 的容器 ID
        :param creator_id: 博主用户 ID
        :return: 包含容器 ID 的字典
        """
        response = await self.get(f"/u/{creator_id}", return_response=True)
        m_weibocn_params = response.cookies.get("M_WEIBOCN_PARAMS")  # 从 Cookie 中获取参数
        if not m_weibocn_params:
            raise DataFetchError("get containerid failed")
        # 解析 Cookie 中的参数字符串
        m_weibocn_params_dict = parse_qs(unquote(m_weibocn_params))
        return {"fid_container_id": m_weibocn_params_dict.get("fid", [""])[0], "lfid_container_id": m_weibocn_params_dict.get("lfid", [""])[0]}

    async def get_creator_info_by_id(self, creator_id: str) -> Dict:
        """
        根据用户 ID 获取博主详情信息
        :param creator_id: 用户 ID
        :return: 博主详情数据
        """
        uri = "/api/container/getIndex"
        containerid = f"100505{creator_id}"  # 构建博主主页容器 ID
        params = {
            "jumpfrom": "weibocom",
            "type": "uid",
            "value": creator_id,
            "containerid":containerid,
        }
        user_res = await self.get(uri, params)
        return user_res

    async def get_notes_by_creator(
        self,
        creator: str,
        container_id: str,
        since_id: str = "0",
    ) -> Dict:
        """
        获取指定博主的帖子列表（单页）
        :param creator: 博主 ID
        :param container_id: 容器 ID
        :param since_id: 上一页最后一条帖子的 ID，用于分页
        :return: 帖子列表数据
        """

        uri = "/api/container/getIndex"
        params = {
            "jumpfrom": "weibocom",
            "type": "uid",
            "value": creator,
            "containerid": container_id,
            "since_id": since_id,
        }
        return await self.get(uri, params)

    async def get_all_notes_by_creator_id(
        self,
        creator_id: str,
        container_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """
        获取指定博主发布的所有帖子，此方法会持续抓取所有分页
        :param creator_id: 博主用户 ID
        :param container_id: 博主的容器 ID
        :param crawl_interval: 请求间隔时间（秒）
        :param callback: 可选的回调函数，用于处理每页获取到的帖子
        :return: 所有帖子列表
        """
        result = []
        notes_has_more = True  # 是否还有更多帖子
        since_id = ""  # 分页游标
        while notes_has_more and len(result) < config.CRAWLER_MAX_NOTES_COUNT:
            notes_res = await self.get_notes_by_creator(creator_id, container_id, since_id)
            if not notes_res:
                utils.logger.error(f"[WeiboClient.get_notes_by_creator] The current creator may have been banned by Weibo, so they cannot access the data.")
                break
            # 获取下一页的分页 ID
            since_id = notes_res.get("cardlistInfo", {}).get("since_id", "0")
            if "cards" not in notes_res:
                utils.logger.info(f"[WeiboClient.get_all_notes_by_creator] No 'notes' key found in response: {notes_res}")
                break

            notes = notes_res["cards"]  # 获取帖子卡片列表
            utils.logger.info(f"[WeiboClient.get_all_notes_by_creator] got user_id:{creator_id} notes len : {len(notes)}")
            # 过滤出 card_type 为 9 的项，这通常代表真实的微博帖子
            notes = [note for note in notes if note.get("card_type") == 9]
            
            # 限制数量
            remaining = config.CRAWLER_MAX_NOTES_COUNT - len(result)
            if remaining <= 0:
                break
            notes_to_add = notes[:remaining]
            
            if callback:
                await callback(notes_to_add)
            await asyncio.sleep(crawl_interval)
            result.extend(notes_to_add)
            # 根据接口返回的总数判断是否继续
            notes_has_more = notes_res.get("cardlistInfo", {}).get("total", 0) > len(result)
        return result

