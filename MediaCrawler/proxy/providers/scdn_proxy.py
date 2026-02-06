# -*- coding: utf-8 -*-
# @Author  : relakkes@gmail.com
# @Time    : 2026/02/04
# @Desc    : SCDN Proxy implementation

from typing import Dict, List
from urllib.parse import urlencode

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

import config
from proxy import IpCache, IpGetError, ProxyProvider
from proxy.types import IpInfoModel, ProviderNameEnum
from tools import utils


class SCDNProxy(ProxyProvider):
    def __init__(self, protocol: str = "all", country_code: str = "all"):
        """
        SCDN Proxy implementation
        Args:
            protocol: Proxy protocol (http, https, socks4, socks5, all)
            country_code: Country code (CN, all, etc.)
        """
        self.proxy_brand_name = ProviderNameEnum.SCDN_PROVIDER.value
        self.api_path = "https://proxy.scdn.io/api/get_proxy.php"
        self.params = {
            "protocol": protocol,
            "country_code": country_code,
        }
        self.ip_cache = IpCache()

    async def get_proxy(self, num: int) -> List[IpInfoModel]:
        """
        Get proxies from cache or API
        """
        try:
            # First try to load from cache
            ip_cache_list = self.ip_cache.load_all_ip(self.proxy_brand_name)
            if len(ip_cache_list) >= num:
                utils.logger.info(f"[SCDNProxy.get_proxy] get {num} proxies from cache")
                return ip_cache_list[:num]
        except Exception as e:
            utils.logger.error(f"[SCDNProxy.get_proxy] load ip from cache err: {e}")

        # If cache is not enough, fetch from API
        return await self._fetch_from_api(num)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def _fetch_from_api(self, count: int) -> List[IpInfoModel]:
        """
        Fetch proxies from API with retry and protocol fallback
        """
        # Protocols to try in order
        initial_protocol = self.params.get("protocol", "all")
        protocols_to_try = [initial_protocol, "all", "http", "https", "socks4"]
        # Remove duplicates while preserving order
        protocols_to_try = list(dict.fromkeys(protocols_to_try))
        
        ip_infos = []
        last_error = None
        
        async with httpx.AsyncClient() as client:
            for proto in protocols_to_try:
                try:
                    current_params = {"protocol": proto, "count": count}
                    if self.params.get("country_code") and self.params.get("country_code") != "all":
                        current_params["country_code"] = self.params.get("country_code")
                    
                    url = self.api_path + '?' + urlencode(current_params)
                    utils.logger.info(f"[SCDNProxy.get_proxy] trying protocol {proto}, url: {url}")
                    response = await client.get(url, timeout=30)
                    
                    res_json = response.json()
                    if res_json.get("code") == 200:
                        data = res_json.get("data", {})
                        proxies = data.get("proxies", [])
                        if not proxies:
                            utils.logger.warning(f"[SCDNProxy.get_proxy] Protocol {proto} returned 0 proxies.")
                            continue
                            
                        for ip_port in proxies:
                            try:
                                ip, port = ip_port.split(":")
                                ip_info_model = IpInfoModel(
                                    ip=ip,
                                    port=int(port),
                                    user="", 
                                    password="",
                                    protocol=proto if proto != "all" else "http",
                                    expired_time_ts=None 
                                )
                                
                                ip_key = f"{self.proxy_brand_name}_{ip_info_model.ip}_{ip_info_model.port}"
                                ip_value = ip_info_model.json()
                                ip_infos.append(ip_info_model)
                                self.ip_cache.set_ip(ip_key, ip_value, ex=300) 
                            except Exception as e:
                                utils.logger.error(f"[SCDNProxy.get_proxy] parse ip_port {ip_port} err: {e}")
                                continue
                        
                        if ip_infos:
                            return ip_infos
                    else:
                        last_error = IpGetError(f"SCDN API error for {proto}: {res_json}")
                        utils.logger.error(last_error)
                except Exception as e:
                    last_error = e
                    utils.logger.error(f"[SCDNProxy.get_proxy] request failed for {proto}: {e}")
                    continue
        
        if not ip_infos:
            raise last_error or IpGetError("All protocols failed to return proxies")
        return ip_infos

    async def get_proxy(self, num: int) -> List[IpInfoModel]:
        """
        Get proxies from SCDN
        Args:
            num: Number of proxies to get
        Returns:
            List of IpInfoModel
        """
        # Prioritize getting IP from cache
        try:
            ip_cache_list = self.ip_cache.load_all_ip(proxy_brand_name=self.proxy_brand_name)
        except Exception as e:
            utils.logger.error(f"[{self.proxy_brand_name}] load cache failed: {e}")
            ip_cache_list = []

        if len(ip_cache_list) >= num:
            return ip_cache_list[:num]

        # If cache is insufficient, get from API
        need_get_count = num - len(ip_cache_list)
        try:
            ip_infos = await self._fetch_from_api(need_get_count)
        except Exception as e:
            utils.logger.error(f"[SCDNProxy.get_proxy] all retries failed: {e}")
            ip_infos = []
                
        return ip_cache_list + ip_infos


def new_scdn_proxy() -> SCDNProxy:
    """
    Construct SCDN Proxy instance
    Returns:
    """
    return SCDNProxy(
        protocol=config.SCDN_PROXY_PROTOCOL,
        country_code=config.SCDN_PROXY_COUNTRY_CODE
    )
