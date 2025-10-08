import aiohttp
import asyncio
from typing import Optional, Dict, List

class RobloxAPI:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def create_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_user_info(self, user_id: int) -> Optional[Dict]:
        await self.create_session()
        try:
            url = f"https://users.roblox.com/v1/users/{user_id}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'id': data.get('id'),
                        'name': data.get('name'),
                        'displayName': data.get('displayName'),
                        'description': data.get('description', ''),
                        'created': data.get('created', ''),
                        'hasVerifiedBadge': data.get('hasVerifiedBadge', False)
                    }
                return None
        except Exception as e:
            print(f"Error getting user info: {e}")
            return None
    
    async def get_user_avatar_url(self, user_id: int) -> Optional[str]:
        await self.create_session()
        try:
            url = f"https://thumbnails.roblox.com/v1/users/avatar?userIds={user_id}&size=420x420&format=Png&isCircular=false"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('data') and len(data['data']) > 0:
                        return data['data'][0].get('imageUrl')
                return None
        except Exception as e:
            print(f"Error getting avatar: {e}")
            return None
    
    async def get_user_presence(self, user_id: int) -> Optional[Dict]:
        await self.create_session()
        try:
            url = "https://presence.roblox.com/v1/presence/users"
            payload = {"userIds": [user_id]}
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('userPresences') and len(data['userPresences']) > 0:
                        presence = data['userPresences'][0]
                        return {
                            'userPresenceType': presence.get('userPresenceType', 0),
                            'lastLocation': presence.get('lastLocation', ''),
                            'placeId': presence.get('placeId'),
                            'rootPlaceId': presence.get('rootPlaceId'),
                            'gameId': presence.get('gameId'),
                            'universeId': presence.get('universeId'),
                            'userId': presence.get('userId'),
                            'lastOnline': presence.get('lastOnline', '')
                        }
                return None
        except Exception as e:
            print(f"Error getting presence: {e}")
            return None
    
    async def get_player_status(self, user_id: int) -> Dict:
        presence = await self.get_user_presence(user_id)
        user_info = await self.get_user_info(user_id)

        if not presence or not user_info:
            return {
                'online': False,
                'status': 'Offline',
                'user_info': user_info
            }

        presence_type = presence['userPresenceType']

        # userPresenceType: 0 = Offline, 1 = Online (website), 2 = Online (in-game), 3 = In Studio
        # Only consider type 2 (in-game) as truly "online" to avoid false positives from website browsing
        if presence_type == 2:
            game_location = presence.get('lastLocation', 'Playing')
            return {
                'online': True,
                'status': 'Online',
                'game': game_location,
                'user_info': user_info,
                'presence': presence
            }
        else:
            return {
                'online': False,
                'status': 'Offline',
                'user_info': user_info,
                'presence': presence
            }