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
# @Author  : Erm
# @Time    : 2024/4/9 17:35
# @Desc    : Weibo media storage
import pathlib
from typing import Dict

import aiofiles

from base.base_crawler import AbstractStoreImage, AbstractStoreVideo
from tools import utils


class WeiboStoreImage(AbstractStoreImage):
    image_store_path: str = "data/weibo/images"

    async def store_image(self, image_content_item: Dict):
        """
        store content

        Args:
            image_content_item:

        Returns:

        """
        await self.save_image(
            picid=image_content_item.get("pic_id"),
            pic_content=image_content_item.get("pic_content"),
            extension_file_name=image_content_item.get("extension_file_name"),
            save_path=image_content_item.get("save_path"),
            save_name=image_content_item.get("save_name")
        )

    def make_save_file_name(self, picid: str, extension_file_name: str, save_path: str = None, save_name: str = None) -> str:
        """
        make save file name by store type

        Args:
            picid: image id
            extension_file_name: video filename with extension
            save_path: custom save path
            save_name: custom save name

        Returns:

        """
        base_path = save_path or self.image_store_path
        final_name = save_name or picid
        return f"{base_path}/{final_name}.{extension_file_name}"

    async def save_image(self, picid: str, pic_content: str, extension_file_name="jpg", save_path: str = None, save_name: str = None):
        """
        save image to local

        Args:
            picid: image id
            pic_content: image content
            extension_file_name: image filename with extension
            save_path: custom save path
            save_name: custom save name

        Returns:

        """
        path = save_path or self.image_store_path
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
        save_file_name = self.make_save_file_name(picid, extension_file_name, save_path, save_name)
        async with aiofiles.open(save_file_name, 'wb') as f:
            await f.write(pic_content)
            utils.logger.info(f"[WeiboImageStoreImplement.save_image] save image {save_file_name} success ...")
