"""Lightline Node — Outline Server API client."""

import aiohttp
import logging

logger = logging.getLogger(__name__)


class OutlineClient:
    """Communicates with the local Outline Server management API."""

    def __init__(self, api_url: str, api_key: str = ''):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key

    async def _request(self, method: str, path: str, **kwargs):
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        url = f'{self.api_url}/{path}'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method, url, headers=headers, ssl=False,
                    timeout=aiohttp.ClientTimeout(total=15), **kwargs
                ) as resp:
                    if resp.content_type == 'application/json':
                        return await resp.json()
                    return {'status': resp.status}
        except Exception as e:
            logger.error(f"Outline API error: {method} {path} — {e}")
            raise

    async def get_server_info(self):
        return await self._request('GET', 'server')

    async def get_access_keys(self):
        return await self._request('GET', 'access-keys')

    async def create_access_key(self, name: str = None):
        data = {'name': name} if name else {}
        return await self._request('POST', 'access-keys', json=data)

    async def delete_access_key(self, key_id: str):
        return await self._request('DELETE', f'access-keys/{key_id}')

    async def rename_access_key(self, key_id: str, name: str):
        return await self._request('PUT', f'access-keys/{key_id}/name', json={'name': name})

    async def set_data_limit(self, key_id: str, limit_bytes: int):
        return await self._request('PUT', f'access-keys/{key_id}/data-limit',
                                   json={'limit': {'bytes': limit_bytes}})

    async def remove_data_limit(self, key_id: str):
        return await self._request('DELETE', f'access-keys/{key_id}/data-limit')

    async def get_metrics(self):
        return await self._request('GET', 'metrics/transfer')

    async def check_health(self) -> bool:
        try:
            info = await self.get_server_info()
            return info is not None and 'name' in info
        except Exception:
            return False
