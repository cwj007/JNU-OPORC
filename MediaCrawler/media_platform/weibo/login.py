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
# @Time    : 2023/12/23 15:42
# @Desc    : Weibo login implementation

import asyncio
import functools
import os
import sys
from typing import Optional

from playwright.async_api import BrowserContext, Page
from tenacity import (RetryError, retry, retry_if_result, stop_after_attempt,
                      wait_fixed)

import config
from base.base_crawler import AbstractLogin
from tools import utils
from tools.cookie_cache import save_cookie_cache


class WeiboLogin(AbstractLogin):
    """
    微博登录实现类，继承自 AbstractLogin
    """
    def __init__(self,
                 login_type: str,  # 登录类型：qrcode, phone, cookie
                 browser_context: BrowserContext,  # 浏览器上下文对象
                 context_page: Page,  # 页面对象
                 login_phone: Optional[str] = "",  # 手机号（如果选手机登录）
                 cookie_str: str = ""  # Cookie 字符串（如果选 Cookie 登录）
                 ):
        config.LOGIN_TYPE = login_type  # 设置全局配置中的登录类型
        self.browser_context = browser_context  # 保存浏览器上下文
        self.context_page = context_page  # 保存页面对象
        self.login_phone = login_phone  # 保存手机号
        self.cookie_str = cookie_str  # 保存 Cookie 字符串
        # 微博 SSO 登录地址
        self.weibo_sso_login_url = "https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog"

    async def begin(self):
        """
        开始执行登录流程
        """
        utils.logger.info("[WeiboLogin.begin] Begin login weibo ...")
        if config.LOGIN_TYPE == "qrcode":
            # 二维码登录
            await self.login_by_qrcode()
        elif config.LOGIN_TYPE == "phone":
            # 手机号登录
            await self.login_by_mobile()
        elif config.LOGIN_TYPE == "cookie":
            # Cookie 登录
            await self.login_by_cookies()
        else:
            # 不支持的登录类型
            raise ValueError(
                "[WeiboLogin.begin] Invalid Login Type Currently only supported qrcode or phone or cookie ...")


    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self, no_logged_in_session: str) -> bool:
        """
        检查当前登录状态是否成功
        :param no_logged_in_session: 未登录时的会话 ID，用于对比变化
        :return: 登录成功返回 True，否则返回 False
        使用 retry 装饰器，如果返回 False 则每秒重试一次，最多重试 600 次（10 分钟）
        """
        current_cookie = await self.browser_context.cookies()  # 获取当前浏览器中的所有 Cookie
        _, cookie_dict = utils.convert_cookies(current_cookie)  # 转换为字典格式
        # 检查 SSOLoginState 标志位
        if cookie_dict.get("SSOLoginState"):
            return True
        # 检查 WBPSESS 会话 ID 是否发生变化，如果变化通常意味着登录成功
        current_web_session = cookie_dict.get("WBPSESS")
        if current_web_session != no_logged_in_session:
            return True
        return False

    async def login_by_qrcode(self):
        """
        通过二维码登录微博并保持登录状态
        """
        utils.logger.info("[WeiboLogin.login_by_qrcode] Begin login weibo by qrcode ...")
        await self.context_page.goto(self.weibo_sso_login_url)  # 跳转到 SSO 登录页面
        # 二维码图片的 CSS 选择器
        qrcode_img_selector = "xpath=//img[@class='w-full h-full']"
        # 等待并获取二维码图片的 Base64 数据
        base64_qrcode_img = await utils.find_login_qrcode(
            self.context_page,
            selector=qrcode_img_selector
        )
        if not base64_qrcode_img:
            # 如果没找到二维码，记录错误并退出
            utils.logger.info("[WeiboLogin.login_by_qrcode] login failed , have not found qrcode please check ....")
            sys.exit()

        # 在控制台或窗口展示二维码供用户扫描
        partial_show_qrcode = functools.partial(utils.show_qrcode, base64_qrcode_img)
        asyncio.get_running_loop().run_in_executor(executor=None, func=partial_show_qrcode)

        utils.logger.info(f"[WeiboLogin.login_by_qrcode] Waiting for scan code login, remaining time is 20s")

        # 获取扫描前的未登录状态下的 Cookie/会话 ID
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = utils.convert_cookies(current_cookie)
        no_logged_in_session = cookie_dict.get("WBPSESS")

        try:
            # 循环检查登录状态直到成功或超时
            await self.check_login_state(no_logged_in_session)
        except RetryError:
            # 如果超过最大重试次数，则登录失败
            utils.logger.info("[WeiboLogin.login_by_qrcode] Login weibo failed by qrcode login method ...")
            sys.exit()

        wait_redirect_seconds = 5  # 登录成功后等待跳转的时间
        utils.logger.info(
            f"[WeiboLogin.login_by_qrcode] Login successful then wait for {wait_redirect_seconds} seconds redirect ...")
        await asyncio.sleep(wait_redirect_seconds)  # 等待页面重定向完成
        # 尝试等待页面加载完成，确保用户信息能够被提取
        try:
            await self.context_page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        await self.save_logged_in_cookie()

    async def save_logged_in_cookie(self):
        """Save logged-in cookies for next time's autofill."""
        try:
            current_cookie = await self.browser_context.cookies()
            cookie_str, _ = utils.convert_cookies(current_cookie)
            
            # Try to get user ID and name from the page or cookies
            user_id = "unknown"
            user_name = "未知用户"
            
            try:
                _, cookie_dict = utils.convert_cookies(current_cookie)
                # 尝试从不同的 Cookie 字段中获取用户 ID
                user_id = cookie_dict.get("uid") or \
                          cookie_dict.get("wb_uid") or \
                          cookie_dict.get("SUID") or \
                          "unknown"
                
                # 尝试从 Cookie 中获取用户名 (unick)
                if "un" in cookie_dict:
                    user_name = cookie_dict.get("un")
                
                # 尝试从 UI 界面获取用户名
                # 微博新旧版 UI 的选择器可能不同
                selectors = [
                    ".woo-box-flex.woo-box-alignCenter.ALink_none_1_3S_",  # 新版 UI 昵称
                    ".gn_name",  # 旧版 UI 昵称
                    ".name",
                    "a[href*='/u/'] span",  # 个人主页链接中的昵称
                    ".nick-name",
                    "xpath=//div[contains(@class, 'woo-box-flex')]//span[contains(@class, 'ALink_none')]"
                ]
                
                for selector in selectors:
                    try:
                        user_name_element = await self.context_page.query_selector(selector)
                        if user_name_element:
                            text = await user_name_element.inner_text()
                            text = text.strip()
                            if text:
                                user_name = text
                                break
                    except Exception:
                        continue
                
                # 如果还是没有获取到 ID，尝试从页面链接获取
                if user_id == "unknown":
                    profile_link = await self.context_page.query_selector("a[href*='/u/']")
                    if profile_link:
                        href = await profile_link.get_attribute("href")
                        if href and "/u/" in href:
                            user_id = href.split("/u/")[-1].split("?")[0]
            except Exception:
                pass
            
            # 从配置获取 Visualized 用户 ID
            visualized_user_id = config.VISUALIZED_USER_ID
            save_cookie_cache("wb", user_id, user_name, cookie_str, visualized_user_id)
            utils.logger.info(f"[WeiboLogin.save_logged_in_cookie] Saved cookie for system user: {visualized_user_id}, platform user: {user_name} ({user_id})")
        except Exception as e:
            utils.logger.error(f"[WeiboLogin.save_logged_in_cookie] Failed to save cookie cache: {e}")

    async def login_by_mobile(self):
        """
        手机号登录（目前尚未实现）
        """
        pass

    async def login_by_cookies(self):
        """
        通过手动提供的 Cookie 字符串登录
        """
        utils.logger.info("[WeiboLogin.login_by_cookies] Begin login weibo by cookie ...")
        # 将 Cookie 字符串转换为字典并逐个添加到浏览器上下文中
        # 注入到 .weibo.cn 和 .weibo.com，确保 PC 和移动端都能识别
        cookie_dict = utils.convert_str_cookie_to_dict(self.cookie_str)
        for key, value in cookie_dict.items():
            for domain in [".weibo.cn", ".weibo.com"]:
                await self.browser_context.add_cookies([{
                    'name': key,
                    'value': value,
                    'domain': domain,
                    'path': "/"
                }])

