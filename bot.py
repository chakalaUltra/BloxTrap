import discord
from discord import app_commands
from discord.ext import tasks
import json
import os
import asyncio
from datetime import datetime
from roblox_api import RobloxAPI

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
roblox_api = RobloxAPI()

DATA_FILE = "data.json"
OWNER_USER_ID = 1117540437016727612

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        "tracked_players": {},
        "notification_channels": {},
        "ping_roles": {}
    }

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

data = load_data()

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
    
    if guild_id not in data["tracked_players"]:
        data["tracked_players"][guild_id] = {}
    
    data["tracked_players"][guild_id][str(user_id)] = {
        "user_id": user_id,
        "username": user_info['name'],
        "display_name": user_info['displayName'],
        "added_at": datetime.utcnow().isoformat(),
        "last_status": "offline",
        "message_id": None
    }
    
    save_data(data)
    
    embed = discord.Embed(
        description=f"✅ Now tracking **{user_info['displayName']}** (@{user_info['name']})\n Profile ID: `{user_id}`",
        color=0xFFFFFF
    )
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="list-tracked", description="Shows all tracked players with a dropdown menu")
async def list_tracked(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    
    if guild_id not in data["tracked_players"] or not data["tracked_players"][guild_id]:
        embed = discord.Embed(
            description="📋 No players are currently being tracked.\nUse `/add-player <roblox_id>` to start tracking players.",
            color=0xFFFFFF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    tracked = data["tracked_players"][guild_id]
    
    class PlayerSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(
                    label=f"{player_data['display_name']} (@{player_data['username']})",
                    description=f"ID: {player_data['user_id']} - Click to remove",
                    value=str(player_id)
                )
                for player_id, player_data in tracked.items()
            ]
            super().__init__(placeholder="Select a player to remove from tracking", options=options, min_values=1, max_values=1)
        
        async def callback(self, interaction: discord.Interaction):
            selected_id = self.values[0]
            player_data = data["tracked_players"][guild_id].pop(selected_id)
            save_data(data)
            
            embed = discord.Embed(
                description=f"✅ Removed **{player_data['display_name']}** (@{player_data['username']}) from tracking.",
                color=0xFFFFFF
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    class PlayerView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(PlayerSelect())
    
    player_list = "\n".join([
        f"• **{p['display_name']}** (@{p['username']}) - ID: `{p['user_id']}`"
        for p in tracked.values()
    ])
    
    embed = discord.Embed(
        title="📋 Tracked Players",
        description=f"{player_list}\n\n**Select a player below to remove them from tracking:**",
        color=0xFFFFFF
    )
    
    await interaction.response.send_message(embed=embed, view=PlayerView(), ephemeral=True)

@tree.command(name="set-channel", description="Sets where notifications are sent")
@app_commands.describe(channel="The channel to send notifications to")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild_id)
    data["notification_channels"][guild_id] = channel.id
    save_data(data)
    
    embed = discord.Embed(
        description=f"✅ Notifications will now be sent to {channel.mention}",
        color=0xFFFFFF
    )
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="set-role", description="Sets which role gets pinged when a player is online")
@app_commands.describe(role="The role to ping for notifications")
async def set_role(interaction: discord.Interaction, role: discord.Role):
    guild_id = str(interaction.guild_id)
    data["ping_roles"][guild_id] = role.id
    save_data(data)
    
    embed = discord.Embed(
        description=f"✅ Will now ping {role.mention} when a tracked player is online",
        color=0xFFFFFF
    )
    
    await interaction.response.send_message(embed=embed)

async def send_or_update_notification(guild_id: str, user_id: str, player_data: dict, status_info: dict):
    user_info = status_info.get('user_info', {})
    username = user_info.get('name', player_data.get('username', 'Unknown'))
    display_name = user_info.get('displayName', player_data.get('display_name', 'Unknown'))
    
    avatar_url = await roblox_api.get_user_avatar_url(int(user_id))
    
    profile_link = f"https://www.roblox.com/users/{user_id}/profile"
    
    is_online = status_info.get('online', False)
    
    if is_online:
        status_text = "Status: Online ✅"
        
        description = (
            f"**[{display_name}]({profile_link})**\n"
            f"━━━━━━ • Profile • ━━━━━━━\n\n"
            f"**{status_text}**"
        )
        
        embed = discord.Embed(
            description=description,
            color=0xFFFFFF,
            timestamp=datetime.utcnow()
        )
        
        if avatar_url:
            embed.set_image(url=avatar_url)
        
        if guild_id not in data["notification_channels"]:
            player_data['last_status'] = 'online'
            save_data(data)
            return
        
        channel_id = data["notification_channels"][guild_id]
        print(f"     → Attempting to fetch channel ID: {channel_id}")
        
        try:
            channel = await client.fetch_channel(channel_id)
            print(f"     → Successfully fetched channel: {channel.name}")
        except Exception as e:
            print(f"     ✗ Failed to fetch channel: {e}")
            player_data['last_status'] = 'online'
            save_data(data)
            return
        
        role_mention = ""
        if guild_id in data["ping_roles"]:
            role_id = data["ping_roles"][guild_id]
            role_mention = f"<@&{role_id}>"
            print(f"     → Will ping role ID: {role_id}")
        
        # Try to fetch and edit existing message, but only if it's in the correct channel
        if player_data.get('message_id'):
            print(f"     → Attempting to edit existing message ID: {player_data['message_id']}")
            try:
                msg = await channel.fetch_message(player_data['message_id'])
                await msg.edit(content=role_mention if role_mention else None, embed=embed)
                print(f"     ✓ Successfully edited message")
            except discord.NotFound:
                print(f"     → Message not found in channel, sending new message")
                msg = await channel.send(content=role_mention if role_mention else None, embed=embed)
                player_data['message_id'] = msg.id
                print(f"     ✓ Sent new message ID: {msg.id}")
            except discord.Forbidden:
                print(f"     → Cannot access message (might be in DMs), sending new message")
                msg = await channel.send(content=role_mention if role_mention else None, embed=embed)
                player_data['message_id'] = msg.id
                print(f"     ✓ Sent new message ID: {msg.id}")
            except Exception as e:
                print(f"     → Error editing message ({type(e).__name__}: {e}), sending new one")
                msg = await channel.send(content=role_mention if role_mention else None, embed=embed)
                player_data['message_id'] = msg.id
                print(f"     ✓ Sent new message ID: {msg.id}")
        else:
            print(f"     → No existing message, sending new one")
            msg = await channel.send(content=role_mention if role_mention else None, embed=embed)
            player_data['message_id'] = msg.id
            print(f"     ✓ Sent new message ID: {msg.id}")
        
        player_data['last_status'] = 'online'
    else:
        status_text = "Status: Offline"
        
        description = (
            f"**[{display_name}]({profile_link})**\n"
            f"━━━━━━ • Profile • ━━━━━━━\n\n"
            f"**{status_text}**"
        )
        
        embed = discord.Embed(
            description=description,
            color=0xFFFFFF,
            timestamp=datetime.utcnow()
        )
        
        if avatar_url:
            embed.set_image(url=avatar_url)
        
        if guild_id not in data["notification_channels"]:
            player_data['last_status'] = 'offline'
            save_data(data)
            return
        
        channel_id = data["notification_channels"][guild_id]
        print(f"     → Attempting to fetch channel ID: {channel_id}")
        
        try:
            channel = await client.fetch_channel(channel_id)
            print(f"     → Successfully fetched channel: {channel.name}")
        except Exception as e:
            print(f"     ✗ Failed to fetch channel: {e}")
            player_data['last_status'] = 'offline'
            save_data(data)
            return
        
        if player_data.get('message_id'):
            print(f"     → Attempting to edit message ID: {player_data['message_id']} to offline")
            try:
                msg = await channel.fetch_message(player_data['message_id'])
                await msg.edit(content=None, embed=embed)
                print(f"     ✓ Successfully edited message to offline")
            except discord.NotFound:
                print(f"     → Message not found in channel, sending new offline notification")
                msg = await channel.send(embed=embed)
                player_data['message_id'] = msg.id
                print(f"     ✓ Sent new offline message ID: {msg.id}")
            except discord.Forbidden:
                print(f"     → Cannot access message (might be in DMs), sending new offline notification")
                msg = await channel.send(embed=embed)
                player_data['message_id'] = msg.id
                print(f"     ✓ Sent new offline message ID: {msg.id}")
            except Exception as e:
                print(f"     → Error editing message ({type(e).__name__}: {e}), sending new offline notification")
                msg = await channel.send(embed=embed)
                player_data['message_id'] = msg.id
                print(f"     ✓ Sent new offline message ID: {msg.id}")
        else:
            print(f"     → No existing message, sending new offline notification")
            msg = await channel.send(embed=embed)
            player_data['message_id'] = msg.id
            print(f"     ✓ Sent offline message ID: {msg.id}")
        
        player_data['last_status'] = 'offline'
    
    save_data(data)

@tasks.loop(seconds=30)
async def check_players():
    print(f"\n{'='*60}")
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Starting player check cycle")
    print(f"{'='*60}")
    
    for guild_id, tracked in data["tracked_players"].items():
        print(f"\nChecking guild {guild_id} - {len(tracked)} player(s) tracked")
        
        for user_id, player_data in tracked.items():
            try:
                status_info = await roblox_api.get_player_status(int(user_id))
                
                current_status = 'online' if status_info.get('online', False) else 'offline'
                
                print(f"\n  → Checking player: {player_data.get('display_name', 'Unknown')} ({user_id})")
                print(f"     Current status: {current_status}, Last status: {player_data.get('last_status')}")
                print(f"     Online: {status_info.get('online', False)}")
                
                if current_status != player_data.get('last_status'):
                    print(f"     ✓ Status changed! Sending notification...")
                    await send_or_update_notification(guild_id, user_id, player_data, status_info)
                elif current_status == 'online':
                    print(f"     ✓ Player is online, updating notification...")
                    await send_or_update_notification(guild_id, user_id, player_data, status_info)
                else:
                    print(f"     - No change, skipping notification")
                
            except Exception as e:
                print(f"     ✗ Error checking player {user_id}: {e}")
            
            await asyncio.sleep(0.5)
    
    print(f"\n{'='*60}")
    print(f"Check cycle completed. Next check in 30 seconds...")
    print(f"{'='*60}\n")

@client.event
async def on_ready():
    await tree.sync()
    print(f'Logged in as {client.user}')
    print(f'Bot is ready! Tracking players...')
    
    if not check_players.is_running():
        check_players.start()

def main():
    token = os.getenv('DISCORD_BOT_TOKEN')
    
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN environment variable not set!")
        print("Please add your Discord bot token to Secrets.")
        return
    
    client.run(token)

if __name__ == "__main__":
    main()
