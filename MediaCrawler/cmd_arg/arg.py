# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/cmd_arg/arg.py
# GitHub: https://github.com/NanmiCoder
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


from __future__ import annotations


import sys
from enum import Enum
from types import SimpleNamespace
from typing import Iterable, Optional, Sequence, Type, TypeVar

import typer
from typing_extensions import Annotated

import config
from tools.utils import str2bool


EnumT = TypeVar("EnumT", bound=Enum)


class PlatformEnum(str, Enum):
    """Supported media platform enumeration"""

    XHS = "xhs"
    DOUYIN = "dy"
    KUAISHOU = "ks"
    BILIBILI = "bili"
    WEIBO = "wb"
    TIEBA = "tieba"
    ZHIHU = "zhihu"


class LoginTypeEnum(str, Enum):
    """Login type enumeration"""

    QRCODE = "qrcode"
    PHONE = "phone"
    COOKIE = "cookie"


class CrawlerTypeEnum(str, Enum):
    """Crawler type enumeration"""

    SEARCH = "search"
    DETAIL = "detail"
    CREATOR = "creator"


class SaveDataOptionEnum(str, Enum):
    """Data save option enumeration"""

    CSV = "csv"
    DB = "db"
    JSON = "json"
    SQLITE = "sqlite"
    MONGODB = "mongodb"
    EXCEL = "excel"
    POSTGRES = "postgres"


class InitDbOptionEnum(str, Enum):
    """Database initialization option"""

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRES = "postgres"


def _to_bool(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    return str2bool(value)


def _coerce_enum(
    enum_cls: Type[EnumT],
    value: EnumT | str,
    default: EnumT,
) -> EnumT:
    """Safely convert a raw config value to an enum member."""

    if isinstance(value, enum_cls):
        return value

    try:
        return enum_cls(value)
    except ValueError:
        typer.secho(
            f"⚠️ 配置值 '{value}' 不在 {enum_cls.__name__} 的支持范围内，将回退到默认值 '{default.value}'。",
            fg=typer.colors.YELLOW,
        )
        return default


def _normalize_argv(argv: Optional[Sequence[str]]) -> Iterable[str]:
    if argv is None:
        return list(sys.argv[1:])
    return list(argv)


def _inject_init_db_default(args: Sequence[str]) -> list[str]:
    """Ensure bare --init_db defaults to sqlite for backward compatibility."""

    normalized: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        normalized.append(arg)

        if arg == "--init_db":
            next_arg = args[i + 1] if i + 1 < len(args) else None
            if not next_arg or next_arg.startswith("-"):
                normalized.append(InitDbOptionEnum.SQLITE.value)
        i += 1

    return normalized


async def parse_cmd(argv: Optional[Sequence[str]] = None):
    """Parse command line arguments using Typer."""

    app = typer.Typer(add_completion=False)

    @app.callback(invoke_without_command=True)
    def main(
        platform: Annotated[
            PlatformEnum,
            typer.Option(
                "--platform",
                help="媒体平台选择 (xhs=小红书 | dy=抖音 | ks=快手 | bili=Bilibili | wb=微博 | tieba=百度贴吧 | zhihu=知乎)",
                rich_help_panel="基础配置",
            ),
        ] = _coerce_enum(PlatformEnum, config.PLATFORM, PlatformEnum.XHS),
        lt: Annotated[
            LoginTypeEnum,
            typer.Option(
                "--lt",
                help="登录类型 (qrcode=二维码 | phone=手机号 | cookie=Cookie)",
                rich_help_panel="账号配置",
            ),
        ] = _coerce_enum(LoginTypeEnum, config.LOGIN_TYPE, LoginTypeEnum.QRCODE),
        crawler_type: Annotated[
            CrawlerTypeEnum,
            typer.Option(
                "--type",
                help="爬虫类型 (search=搜索 | detail=详情 | creator=创作者)",
                rich_help_panel="基础配置",
            ),
        ] = _coerce_enum(CrawlerTypeEnum, config.CRAWLER_TYPE, CrawlerTypeEnum.SEARCH),
        start: Annotated[
            int,
            typer.Option(
                "--start",
                help="起始页码",
                rich_help_panel="基础配置",
            ),
        ] = config.START_PAGE,
        keywords: Annotated[
            str,
            typer.Option(
                "--keywords",
                help="输入关键词，多个关键词用逗号分隔",
                rich_help_panel="基础配置",
            ),
        ] = config.KEYWORDS,
        get_comment: Annotated[
            str,
            typer.Option(
                "--get_comment",
                help="是否爬取一级评论，支持 yes/true/t/y/1 或 no/false/f/n/0",
                rich_help_panel="评论配置",
                show_default=True,
            ),
        ] = str(config.ENABLE_GET_COMMENTS),
        get_sub_comment: Annotated[
            str,
            typer.Option(
                "--get_sub_comment",
                help="是否爬取二级评论，支持 yes/true/t/y/1 或 no/false/f/n/0",
                rich_help_panel="评论配置",
                show_default=True,
            ),
        ] = str(config.ENABLE_GET_SUB_COMMENTS),
        headless: Annotated[
            str,
            typer.Option(
                "--headless",
                help="是否启用无头模式（适用于 Playwright 和 CDP），支持 yes/true/t/y/1 或 no/false/f/n/0",
                rich_help_panel="运行配置",
                show_default=True,
            ),
        ] = str(config.HEADLESS),
        save_data_option: Annotated[
            SaveDataOptionEnum,
            typer.Option(
                "--save_data_option",
                help="数据保存选项 (csv=CSV文件 | db=MySQL数据库 | json=JSON文件 | sqlite=SQLite数据库 | mongodb=MongoDB数据库 | excel=Excel文件 | postgres=PostgreSQL数据库)",
                rich_help_panel="存储配置",
            ),
        ] = _coerce_enum(
            SaveDataOptionEnum, config.SAVE_DATA_OPTION, SaveDataOptionEnum.JSON
        ),
        init_db: Annotated[
            Optional[InitDbOptionEnum],
            typer.Option(
                "--init_db",
                help="初始化数据库表结构 (sqlite | mysql | postgres)",
                rich_help_panel="存储配置",
            ),
        ] = None,
        cookies: Annotated[
            str,
            typer.Option(
                "--cookies",
                help="用于Cookie登录方法的Cookie值",
                rich_help_panel="账号配置",
            ),
        ] = config.COOKIES,
        specified_id: Annotated[
            str,
            typer.Option(
                "--specified_id",
                help="详情模式下的帖子/视频ID列表，多个ID用逗号分隔（支持完整URL或ID）",
                rich_help_panel="基础配置",
            ),
        ] = "",
        creator_id: Annotated[
            str,
            typer.Option(
                "--creator_id",
                help="创作者模式下的创作者ID列表，多个ID用逗号分隔（支持完整URL或ID）",
                rich_help_panel="基础配置",
            ),
        ] = "",
        max_comments_count_singlenotes: Annotated[
            int,
            typer.Option(
                "--max_comments_count_singlenotes",
                help="每篇帖子/视频爬取的最大一级评论数量",
                rich_help_panel="评论配置",
            ),
        ] = config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
        max_concurrency_num: Annotated[
            int,
            typer.Option(
                "--max_concurrency_num",
                help="最大并发爬虫数量",
                rich_help_panel="性能配置",
            ),
        ] = config.MAX_CONCURRENCY_NUM,
        enable_ip_proxy: Annotated[
            str,
            typer.Option(
                "--enable_ip_proxy",
                help="是否启用 IP 代理，支持 yes/true/t/y/1 或 no/false/f/n/0",
                rich_help_panel="代理配置",
                show_default=True,
            ),
        ] = str(config.ENABLE_IP_PROXY),
        ip_proxy_pool_count: Annotated[
            int,
            typer.Option(
                "--ip_proxy_pool_count",
                help="代理 IP 池数量",
                rich_help_panel="代理配置",
            ),
        ] = config.IP_PROXY_POOL_COUNT,
        enable_validate_ip: Annotated[
            str,
            typer.Option(
                "--enable_validate_ip",
                help="是否开启 IP 代理验证，支持 yes/true/t/y/1 或 no/false/f/n/0",
                rich_help_panel="代理配置",
                show_default=True,
            ),
        ] = str(config.ENABLE_VALIDATE_IP),
        ip_proxy_provider_name: Annotated[
            str,
            typer.Option(
                "--ip_proxy_provider_name",
                help="代理 IP 提供商名称 (kuaidaili | wandouhttp)",
                rich_help_panel="代理配置",
            ),
        ] = config.IP_PROXY_PROVIDER_NAME,
        wandou_app_key: Annotated[
            str,
            typer.Option(
                "--wandou_app_key",
                help="豌豆代理 App Key",
                rich_help_panel="代理配置",
            ),
        ] = config.WANDOU_APP_KEY,
        kdl_secret_id: Annotated[
            str,
            typer.Option(
                "--kdl_secret_id",
                help="快代理 Secret ID",
                rich_help_panel="代理配置",
            ),
        ] = config.KDL_SECRET_ID,
        kdl_signature: Annotated[
            str,
            typer.Option(
                "--kdl_signature",
                help="快代理 Signature",
                rich_help_panel="代理配置",
            ),
        ] = config.KDL_SIGNATURE,
        kdl_user_name: Annotated[
            str,
            typer.Option(
                "--kdl_user_name",
                help="快代理用户名",
                rich_help_panel="代理配置",
            ),
        ] = config.KDL_USER_NAME,
        kdl_user_pwd: Annotated[
            str,
            typer.Option(
                "--kdl_user_pwd",
                help="快代理密码",
                rich_help_panel="代理配置",
            ),
        ] = config.KDL_USER_PWD,
        crawler_max_notes_count: Annotated[
            int,
            typer.Option(
                "--crawler_max_notes_count",
                help="爬取视频/帖子的数量控制",
                rich_help_panel="基础配置",
            ),
        ] = config.CRAWLER_MAX_NOTES_COUNT,
        weibo_search_type: Annotated[
            str,
            typer.Option(
                "--weibo_search_type",
                help="微博搜索类型 (default | real_time | popular | video)",
                rich_help_panel="微博配置",
            ),
        ] = config.WEIBO_SEARCH_TYPE,
    ) -> SimpleNamespace:
        """MediaCrawler 命令行入口"""

        enable_comment = _to_bool(get_comment)
        enable_sub_comment = _to_bool(get_sub_comment)
        enable_headless = _to_bool(headless)
        enable_ip_proxy_bool = _to_bool(enable_ip_proxy)
        enable_validate_ip_bool = _to_bool(enable_validate_ip)
        init_db_value = init_db.value if init_db else None

        # Parse specified_id and creator_id into lists
        specified_id_list = [id.strip() for id in specified_id.split(",") if id.strip()] if specified_id else []
        creator_id_list = [id.strip() for id in creator_id.split(",") if id.strip()] if creator_id else []

        # override global config
        config.PLATFORM = platform.value
        config.LOGIN_TYPE = lt.value
        config.CRAWLER_TYPE = crawler_type.value
        config.START_PAGE = start
        config.KEYWORDS = keywords
        config.ENABLE_GET_COMMENTS = enable_comment
        config.ENABLE_GET_SUB_COMMENTS = enable_sub_comment
        config.HEADLESS = enable_headless
        config.CDP_HEADLESS = enable_headless
        config.SAVE_DATA_OPTION = save_data_option.value
        config.COOKIES = cookies
        config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = max_comments_count_singlenotes
        config.MAX_CONCURRENCY_NUM = max_concurrency_num
        
        # New configuration overrides
        config.ENABLE_IP_PROXY = enable_ip_proxy_bool
        config.IP_PROXY_POOL_COUNT = ip_proxy_pool_count
        config.ENABLE_VALIDATE_IP = enable_validate_ip_bool
        config.IP_PROXY_PROVIDER_NAME = ip_proxy_provider_name
        config.WANDOU_APP_KEY = wandou_app_key
        config.KDL_SECRET_ID = kdl_secret_id
        config.KDL_SIGNATURE = kdl_signature
        config.KDL_USER_NAME = kdl_user_name
        config.KDL_USER_PWD = kdl_user_pwd
        config.CRAWLER_MAX_NOTES_COUNT = crawler_max_notes_count
        config.WEIBO_SEARCH_TYPE = weibo_search_type

        # Set platform-specific ID lists for detail/creator mode
        config.IS_CLI_SPECIFIED_ID = bool(specified_id_list)
        if specified_id_list:
            if platform == PlatformEnum.XHS:
                config.XHS_SPECIFIED_NOTE_URL_LIST = specified_id_list
            elif platform == PlatformEnum.BILIBILI:
                config.BILI_SPECIFIED_ID_LIST = specified_id_list
            elif platform == PlatformEnum.DOUYIN:
                config.DY_SPECIFIED_ID_LIST = specified_id_list
            elif platform == PlatformEnum.WEIBO:
                # 按照用户要求，微博的 specified_id 统一存入 WEIBO_CREATOR_ID_LIST
                config.WEIBO_CREATOR_ID_LIST = specified_id_list
                config.WEIBO_SPECIFIED_ID_LIST = specified_id_list
            elif platform == PlatformEnum.KUAISHOU:
                config.KS_SPECIFIED_ID_LIST = specified_id_list
            elif platform == PlatformEnum.ZHIHU:
                config.ZHIHU_SPECIFIED_ID_LIST = specified_id_list

        if creator_id_list:
            if platform == PlatformEnum.XHS:
                config.XHS_CREATOR_ID_LIST = creator_id_list
            elif platform == PlatformEnum.BILIBILI:
                config.BILI_CREATOR_ID_LIST = creator_id_list
            elif platform == PlatformEnum.DOUYIN:
                config.DY_CREATOR_ID_LIST = creator_id_list
            elif platform == PlatformEnum.WEIBO:
                config.WEIBO_CREATOR_ID_LIST = creator_id_list
            elif platform == PlatformEnum.KUAISHOU:
                config.KS_CREATOR_ID_LIST = creator_id_list
            elif platform == PlatformEnum.ZHIHU:
                config.ZHIHU_CREATOR_URL_LIST = creator_id_list

        return SimpleNamespace(
            platform=config.PLATFORM,
            lt=config.LOGIN_TYPE,
            type=config.CRAWLER_TYPE,
            start=config.START_PAGE,
            keywords=config.KEYWORDS,
            get_comment=config.ENABLE_GET_COMMENTS,
            get_sub_comment=config.ENABLE_GET_SUB_COMMENTS,
            headless=config.HEADLESS,
            save_data_option=config.SAVE_DATA_OPTION,
            init_db=init_db_value,
            cookies=config.COOKIES,
            specified_id=specified_id,
            creator_id=creator_id,
        )

    command = typer.main.get_command(app)

    cli_args = _normalize_argv(argv)
    cli_args = _inject_init_db_default(cli_args)

    try:
        result = command.main(args=cli_args, standalone_mode=False)
        if isinstance(result, int):  # help/options handled by Typer; propagate exit code
            raise SystemExit(result)
        return result
    except typer.Exit as exc:  # pragma: no cover - CLI exit paths
        raise SystemExit(exc.exit_code) from exc
