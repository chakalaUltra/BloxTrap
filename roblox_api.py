import aiohttp
import asyncio
from typing import Optional, Dict, List
import time
import logging

logger = logging.getLogger(__name__)

class RobloxAPI:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, tuple] = {}
        self.cache_ttl = {'user_info': 300, 'avatar': 300, 'presence': 20}
        self.rate_limit_delay = 0.2
        self.last_request_time = 0

    async def create_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=20)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _get_cached(self, cache_key: str, cache_type: str):
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl.get(cache_type, 60):
                return data
            del self.cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, data):
        self.cache[cache_key] = (data, time.time())
        if len(self.cache) > 800:
            oldest = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest]

    async def _rate_limit(self):
        current = time.time()
        if current - self.last_request_time < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - (current - self.last_request_time))
        self.last_request_time = time.time()

    async def _make_request(self, method: str, url: str, **kwargs) -> Optional[Dict]:
        await self.create_session()
        await self._rate_limit()
        for attempt in range(3):
            try:
                async with self.session.request(method, url, **kwargs) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        retry = int(resp.headers.get('Retry-After', 5))
                        logger.warning(f"Rate limited, waiting {retry}s")
                        await asyncio.sleep(retry)
                        continue
                    elif resp.status >= 400:
                        logger.error(f"API error {resp.status} for {url}")
                        return None
            except Exception as e:
                logger.error(f"Request error (attempt {attempt+1}): {e}")
                if attempt < 2:
                    await asyncio.sleep(1 * (attempt + 1))
        return None

    async def get_user_info(self, user_id: int) -> Optional[Dict]:
        cache_key = f"user_info_{user_id}"
        cached = self._get_cached(cache_key, 'user_info')
        if cached:
            return cached
        url = f"https://users.roblox.com/v1/users/{user_id}"
        data = await self._make_request('GET', url)
        if data:
            result = {
                'id': data.get('id'), 'name': data.get('name'), 'displayName': data.get('displayName'),
                'description': data.get('description', ''), 'created': data.get('created')
            }
            self._set_cache(cache_key, result)
            return result
        return None

    async def get_user_avatar_url(self, user_id: int) -> Optional[str]:
        cache_key = f"avatar_{user_id}"
        cached = self._get_cached(cache_key, 'avatar')
        if cached:
            return cached
        url = f"https://thumbnails.roblox.com/v1/users/avatar?userIds={user_id}&size=420x420&format=Png"
        data = await self._make_request('GET', url)
        if data and data.get('data'):
            avatar_url = data['data'][0].get('imageUrl')
            self._set_cache(cache_key, avatar_url)
            return avatar_url
        return None

    async def get_user_presence(self, user_id: int) -> Optional[Dict]:
        cache_key = f"presence_{user_id}"
        cached = self._get_cached(cache_key, 'presence')
        if cached:
            return cached
        url = "https://presence.roblox.com/v1/presence/users"
        data = await self._make_request('POST', url, json={"userIds": [user_id]})
        if data and data.get('userPresences'):
            presence = data['userPresences'][0]
            result = {k: presence.get(k) for k in ['userPresenceType', 'lastLocation', 'placeId', 'rootPlaceId']}
            self._set_cache(cache_key, result)
            return result
        return None

    async def get_player_status(self, user_id: int) -> Dict:
        presence = await self.get_user_presence(user_id)
        user_info = await self.get_user_info(user_id)
        online = presence and presence.get('userPresenceType') == 2
        return {
            'online': online,
            'status': 'Online' if online else 'Offline',
            'game': presence.get('lastLocation') if online else None,
            'user_info': user_info or {},
            'presence': presence or {}
        }

    async def get_multiple_user_presences(self, user_ids: List[int]) -> Dict[int, Optional[Dict]]:
        if not user_ids:
            return {}
        results = {}
        batch_size = 100
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i+batch_size]
            data = await self._make_request('POST', "https://presence.roblox.com/v1/presence/users", json={"userIds": batch})
            if data and data.get('userPresences'):
                for p in data['userPresences']:
                    uid = p.get('userId')
                    if uid:
                        results[uid] = {k: p.get(k) for k in ['userPresenceType', 'lastLocation', 'placeId', 'rootPlaceId']}
        return results

    def clear_cache(self):
        self.cache.clear()
