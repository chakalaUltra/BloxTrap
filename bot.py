import discord
from discord import app_commands
from discord.ext import tasks
import os
import asyncio
from datetime import datetime
from roblox_api import RobloxAPI
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
roblox_api = RobloxAPI()

# MongoDB Setup
MONGODB_URI = os.getenv('DATABASE')
if not MONGODB_URI:
    logger.error("DATABASE environment variable not set!")

mongo_client = AsyncIOMotorClient(MONGODB_URI)

try:
    db = mongo_client.get_default_database()
except Exception:
    db = mongo_client.bloxtrap_bot

guild_settings = db.guild_settings
tracked_players = db.tracked_players

OWNER_USER_ID = 1117540437016727612

def create_embed(title: str, description: str, color: int = 0x2b2d31, footer: str = None) -> discord.Embed:
    """Improved embed creator with better Discord dark theme color."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow()
    )
    if footer:
        embed.set_footer(text=footer)
    return embed

@tree.command(name="add-player", description="Add a Roblox player to track")
@app_commands.describe(roblox_id="Roblox user ID to track")
async def add_player(interaction: discord.Interaction, roblox_id: str):
    await interaction.response.defer(ephemeral=True)
    try:
        user_id = int(roblox_id.strip())
    except ValueError:
        embed = create_embed("❌ Error", "Invalid Roblox ID. Use numbers only.", 0xff0000)
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    user_info = await roblox_api.get_user_info(user_id)
    if not user_info:
        embed = create_embed("❌ Not Found", f"Roblox user {user_id} not found.", 0xff0000)
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    await tracked_players.update_one(
        {"guild_id": guild_id, "roblox_id": str(user_id)},
        {"$set": {
            "username": user_info.get('name'),
            "display_name": user_info.get('displayName'),
            "added_at": datetime.utcnow().isoformat(),
            "last_status": "offline"
        }},
        upsert=True
    )

    embed = create_embed(
        "✅ Tracking Added",
        f"**{user_info.get('displayName', 'Unknown')}** (@{user_info.get('name', 'N/A')})\nID: `{user_id}`",
        0x00ff00
    )
    await interaction.followup.send(embed=embed)

@tree.command(name="list-tracked", description="List and manage tracked players")
async def list_tracked(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    cursor = tracked_players.find({"guild_id": guild_id})
    players = await cursor.to_list(length=50)

    if not players:
        embed = create_embed("📋 No Players", "Use `/add-player` to start tracking.", 0x2b2d31)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    class PlayerSelect(discord.ui.Select):
        def __init__(self, players_list, g_id):
            self.guild_id = g_id
            options = [
                discord.SelectOption(
                    label=f"{p.get('display_name', p.get('username', 'Unknown'))}",
                    description=f"ID: {p['roblox_id']}",
                    value=p['roblox_id']
                ) for p in players_list
            ]
            super().__init__(placeholder="Select player to remove", options=options, min_values=1, max_values=1)

        async def callback(self, inter: discord.Interaction):
            selected = self.values[0]
            await tracked_players.delete_one({"guild_id": self.guild_id, "roblox_id": selected})
            embed = create_embed("✅ Removed", f"Player {selected} removed from tracking.", 0x00ff00)
            await inter.response.send_message(embed=embed, ephemeral=True)

    view = discord.ui.View()
    view.add_item(PlayerSelect(players, guild_id))

    player_list = "\n".join([f"• **{p.get('display_name')}** (@{p.get('username')}) - `{p['roblox_id']}`" for p in players])
    embed = create_embed("📋 Tracked Players", player_list + "\n\nSelect below to remove:")
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@tree.command(name="set-channel", description="Set notification channel")
@app_commands.describe(channel="Notification channel")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild_id)
    await guild_settings.update_one(
        {"guild_id": guild_id},
        {"$set": {"notification_channel_id": channel.id}},
        upsert=True
    )
    embed = create_embed("✅ Channel Set", f"Notifications → {channel.mention}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="set-role", description="Set ping role for online notifications")
@app_commands.describe(role="Role to ping")
async def set_role(interaction: discord.Interaction, role: discord.Role):
    guild_id = str(interaction.guild_id)
    await guild_settings.update_one(
        {"guild_id": guild_id},
        {"$set": {"ping_role_id": role.id}},
        upsert=True
    )
    embed = create_embed("✅ Role Set", f"Will ping {role.mention} on online events.")
    await interaction.response.send_message(embed=embed)

class JoinServerButton(discord.ui.View):
    def __init__(self, place_id: int, user_id: int):
        super().__init__(timeout=None)
        join_url = f"https://www.roblox.com/games/start?placeId={place_id}&launchData=user:{user_id}"
        self.add_item(discord.ui.Button(label="Join Server", style=discord.ButtonStyle.blurple, url=join_url))

async def send_online_notification(guild_id: str, user_id: str, player_data: dict, status_info: dict):
    user_info = status_info.get('user_info', {})
    display_name = user_info.get('displayName', player_data.get('display_name', 'Unknown'))
    avatar_url = await roblox_api.get_user_avatar_url(int(user_id))
    profile_link = f"https://www.roblox.com/users/{user_id}/profile"

    description = f"**[{display_name}]({profile_link})** is now **Online** ✅\n\n"
    if status_info.get('game'):
        description += f"**Playing:** {status_info.get('game', 'Unknown')}\n"

    embed = create_embed("🟢 Player Online", description, color=0x00ff00)
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)

    settings = await guild_settings.find_one({"guild_id": guild_id})
    if not settings or not settings.get('notification_channel_id'):
        return

    try:
        channel = await client.fetch_channel(settings['notification_channel_id'])
        role_mention = f"<@&{settings['ping_role_id']}>" if settings.get('ping_role_id') else ""
        place_id = status_info.get('presence', {}).get('placeId')
        view = JoinServerButton(place_id, int(user_id)) if place_id else None

        msg = await channel.send(content=role_mention, embed=embed, view=view)
        await tracked_players.update_one(
            {"guild_id": guild_id, "roblox_id": user_id},
            {"$set": {"message_id": msg.id, "last_status": "online"}}
        )
    except Exception as e:
        logger.error(f"Notification failed: {e}")

async def update_offline_notification(guild_id: str, user_id: str, player_data: dict):
    if not player_data.get('message_id'):
        return
    settings = await guild_settings.find_one({"guild_id": guild_id})
    if not settings or not settings.get('notification_channel_id'):
        return
    try:
        channel = await client.fetch_channel(settings['notification_channel_id'])
        msg = await channel.fetch_message(player_data['message_id'])
        display_name = player_data.get('display_name', 'Unknown')
        avatar_url = await roblox_api.get_user_avatar_url(int(user_id))
        profile_link = f"https://www.roblox.com/users/{user_id}/profile"

        embed = create_embed("🔴 Player Offline", f"**[{display_name}]({profile_link})** is now **Offline** ❌", color=0xff0000)
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        await msg.edit(content=None, embed=embed, view=None)
        await tracked_players.update_one(
            {"guild_id": guild_id, "roblox_id": user_id},
            {"$set": {"message_id": None, "last_status": "offline"}}
        )
    except Exception as e:
        logger.warning(f"Offline update failed: {e}")

@tasks.loop(seconds=45)  # Slightly longer interval for stability
async def check_players():
    try:
        cursor = tracked_players.find({})
        all_players = await cursor.to_list(length=500)

        if not all_players:
            return

        user_ids = [int(p['roblox_id']) for p in all_players]
        presences = await roblox_api.get_multiple_user_presences(user_ids)

        for player_data in all_players:
            user_id = player_data['roblox_id']
            guild_id = player_data['guild_id']
            presence = presences.get(int(user_id))
            current_online = bool(presence and presence.get('userPresenceType') == 2)

            last_status = player_data.get('last_status', 'offline')

            if current_online and last_status != 'online':
                status_info = await roblox_api.get_player_status(int(user_id))
                await send_online_notification(guild_id, user_id, player_data, status_info)
            elif not current_online and last_status == 'online':
                await update_offline_notification(guild_id, user_id, player_data)

            await tracked_players.update_one(
                {"guild_id": guild_id, "roblox_id": user_id},
                {"$set": {"last_status": "online" if current_online else "offline"}}
            )
    except Exception as e:
        logger.error(f"Check players error: {e}")

@check_players.before_loop
async def before_check_players():
    await client.wait_until_ready()

@client.event
async def on_ready():
    await tree.sync()
    logger.info(f'✅ BloxTrap logged in as {client.user}')
    if not check_players.is_running():
        check_players.start()

    # Set rich presence
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Roblox Players"))

async def health_check(request):
    return web.Response(text="BloxTrap is running! ✅")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    port = int(os.getenv('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server running on port {port}")

async def main():
    await roblox_api.create_session()
    try:
        await asyncio.gather(
            client.start(os.getenv('TOKEN')),
            start_web_server()
        )
    finally:
        await roblox_api.close_session()

if __name__ == "__main__":
    asyncio.run(main())
