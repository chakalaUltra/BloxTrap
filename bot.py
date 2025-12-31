import discord
from discord import app_commands
from discord.ext import tasks
import os
import asyncio
from datetime import datetime
from roblox_api import RobloxAPI
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
roblox_api = RobloxAPI()

# MongoDB Setup
MONGODB_URI = os.getenv('DATABASE')
mongo_client = AsyncIOMotorClient(MONGODB_URI)

# Attempt to handle URIs without a default database specified
try:
    db = mongo_client.get_default_database()
except Exception:
    # Fallback to a named database if not specified in URI
    db = mongo_client.bloxtrap_bot

guild_settings = db.guild_settings
tracked_players = db.tracked_players

OWNER_USER_ID = 1117540437016727612

@tree.command(name="add-player", description="Add a Roblox player to track by their user ID")
@app_commands.describe(roblox_id="The Roblox user ID (Profile ID) to track")
async def add_player(interaction: discord.Interaction, roblox_id: str):
    try:
        user_id = int(roblox_id)
    except ValueError:
        embed = discord.Embed(
            description="❌ Invalid Roblox ID. Please provide a valid Profile ID (numbers only).",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    user_info = await roblox_api.get_user_info(user_id)
    
    if not user_info:
        embed = discord.Embed(
            description=f"❌ Could not find Roblox user with ID: {user_id}",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    guild_id = str(interaction.guild_id)
    
    await tracked_players.update_one(
        {"guild_id": guild_id, "roblox_id": str(user_id)},
        {
            "$set": {
                "username": user_info['name'],
                "display_name": user_info['displayName'],
                "added_at": datetime.utcnow().isoformat(),
                "last_status": "offline"
            }
        },
        upsert=True
    )
    
    embed = discord.Embed(
        description=f"✅ Now tracking **{user_info['displayName']}** (@{user_info['name']})\n Profile ID: `{user_id}`",
        color=0xFFFFFF
    )
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="list-tracked", description="Shows all tracked players with a dropdown menu")
async def list_tracked(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    
    cursor = tracked_players.find({"guild_id": guild_id})
    players = await cursor.to_list(length=100)
    
    if not players:
        embed = discord.Embed(
            description="📋 No players are currently being tracked.\nUse `/add-player <roblox_id>` to start tracking players.",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    class PlayerSelect(discord.ui.Select):
        def __init__(self, players, guild_id):
            self.guild_id = guild_id
            options = [
                discord.SelectOption(
                    label=f"{p['display_name']} (@{p['username']})",
                    description=f"ID: {p['roblox_id']} - Click to remove",
                    value=p['roblox_id']
                )
                for p in players
            ]
            super().__init__(placeholder="Select a player to remove from tracking", options=options, min_values=1, max_values=1)
        
        async def callback(self, interaction: discord.Interaction):
            selected_id = self.values[0]
            
            player_data = await tracked_players.find_one({"guild_id": self.guild_id, "roblox_id": selected_id})
            
            if player_data:
                # Delete old message if exists
                if player_data.get('message_id'):
                    settings = await guild_settings.find_one({"guild_id": self.guild_id})
                    if settings and settings.get('notification_channel_id'):
                        try:
                            channel = await client.fetch_channel(settings['notification_channel_id'])
                            msg = await channel.fetch_message(player_data['message_id'])
                            await msg.delete()
                        except:
                            pass
                
                # Remove from tracking
                await tracked_players.delete_one({"guild_id": self.guild_id, "roblox_id": selected_id})
                
                embed = discord.Embed(
                    description=f"✅ Removed **{player_data['display_name']}** (@{player_data['username']}) from tracking.",
                    color=0xFFFFFF
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    description="❌ Player not found in tracking list.",
                    color=0xFFFFFF
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
    
    class PlayerView(discord.ui.View):
        def __init__(self, players, guild_id):
            super().__init__()
            self.add_item(PlayerSelect(players, guild_id))
    
    player_list = "\n".join([
        f"• **{p['display_name']}** (@{p['username']}) - ID: `{p['roblox_id']}`"
        for p in players
    ])
    
    embed = discord.Embed(
        title="📋 Tracked Players",
        description=f"{player_list}\n\n**Select a player below to remove them from tracking:**",
        color=0xFFFFFF
    )
    
    await interaction.response.send_message(embed=embed, view=PlayerView(players, guild_id), ephemeral=True)

@tree.command(name="set-channel", description="Sets where notifications are sent")
@app_commands.describe(channel="The channel to send notifications to")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild_id)
    
    await guild_settings.update_one(
        {"guild_id": guild_id},
        {"$set": {"notification_channel_id": channel.id}},
        upsert=True
    )
    
    embed = discord.Embed(
        description=f"✅ Notifications will now be sent to {channel.mention}",
        color=0xFFFFFF
    )
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="set-role", description="Sets which role gets pinged when a player is online")
@app_commands.describe(role="The role to ping for notifications")
async def set_role(interaction: discord.Interaction, role: discord.Role):
    guild_id = str(interaction.guild_id)
    
    await guild_settings.update_one(
        {"guild_id": guild_id},
        {"$set": {"ping_role_id": role.id}},
        upsert=True
    )
    
    embed = discord.Embed(
        description=f"✅ Will now ping {role.mention} when a tracked player is online",
        color=0xFFFFFF
    )
    
    await interaction.response.send_message(embed=embed)

class JoinServerButton(discord.ui.View):
    def __init__(self, place_id: int, user_id: int):
        super().__init__(timeout=None)
        self.place_id = place_id
        self.user_id = user_id
        
        join_url = f"https://www.roblox.com/games/start?placeId={place_id}&launchData=user:{user_id}"
        button = discord.ui.Button(
            label="Join Server",
            style=discord.ButtonStyle.gray,
            url=join_url
        )
        self.add_item(button)

async def send_online_notification(guild_id: str, user_id: str, player_data: dict, status_info: dict):
    user_info = status_info.get('user_info', {})
    display_name = user_info.get('displayName', player_data.get('display_name', 'Unknown'))
    
    avatar_url = await roblox_api.get_user_avatar_url(int(user_id))
    profile_link = f"https://www.roblox.com/users/{user_id}/profile"
    
    description = (
        f"**[{display_name}]({profile_link})**\n"
        f"━━━━━━ • Profile • ━━━━━━━\n\n"
        f"**Status: Online ✅**"
    )
    
    embed = discord.Embed(
        description=description,
        color=0xFFFFFF,
        timestamp=datetime.utcnow()
    )
    
    if avatar_url:
        embed.set_image(url=avatar_url)
    
    settings = await guild_settings.find_one({"guild_id": guild_id})

    if not settings or not settings.get('notification_channel_id'):
        return
    
    try:
        channel = await client.fetch_channel(settings['notification_channel_id'])
    except Exception as e:
        print(f"Failed to fetch channel: {e}")
        return
    
    role_mention = ""
    if settings.get('ping_role_id'):
        role_mention = f"<@&{settings['ping_role_id']}>"
    
    presence = status_info.get('presence', {})
    place_id = presence.get('placeId')
    view = JoinServerButton(place_id=place_id, user_id=int(user_id)) if place_id else None
    
    msg = await channel.send(content=role_mention if role_mention else None, embed=embed, view=view)
    
    await tracked_players.update_one(
        {"guild_id": guild_id, "roblox_id": user_id},
        {"$set": {"message_id": msg.id}}
    )

@tasks.loop(seconds=15)
async def check_players():
    try:
        cursor = tracked_players.find({})
        all_players = await cursor.to_list(length=1000)
        
        for player_data in all_players:
            guild_id = player_data['guild_id']
            user_id = player_data['roblox_id']
            
            try:
                # Force clear cache for presence to get the most up-to-date status
                roblox_api.clear_cache('presence')
                
                status_info = await roblox_api.get_player_status(int(user_id))
                current_status = 'online' if status_info.get('online', False) else 'offline'
                
                # Only send notification when player goes from offline to online
                if current_status == 'online' and player_data.get('last_status') != 'online':
                    await send_online_notification(guild_id, user_id, player_data, status_info)
                
                # Update status in database
                await tracked_players.update_one(
                    {"guild_id": guild_id, "roblox_id": user_id},
                    {"$set": {"last_status": current_status}}
                )
                
            except Exception as e:
                print(f"Error checking player {user_id}: {e}")
            
            await asyncio.sleep(0.1)
                
    except Exception as e:
        print(f"Error in check_players loop: {e}")

@check_players.before_loop
async def before_check_players():
    await client.wait_until_ready()

@client.event
async def on_ready():
    await tree.sync()
    print(f'Logged in as {client.user}', flush=True)
    
    if not check_players.is_running():
        check_players.start()

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    port = int(os.getenv('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f'Health check server running on port {port}', flush=True)

async def main():
    token = os.getenv('DISCORD_BOT_TOKEN')
    
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN environment variable not set!")
        return
    
    if not MONGODB_URI:
        print("ERROR: DATABASE environment variable (MongoDB URI) not set!")
        return
    
    await start_web_server()
    await client.start(token)

if __name__ == "__main__":
    asyncio.run(main())