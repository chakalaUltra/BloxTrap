# Overview

This is a Discord bot that tracks Roblox players' online status and game activity. The bot monitors when tracked players join or leave specific Roblox games (specifically "The Strongest Battlegrounds") and sends notifications to designated Discord channels. It uses Discord's slash commands for user interaction and maintains persistent data storage for tracking configurations.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Bot Framework
- **Discord.py Library**: Uses discord.py with app_commands for slash command functionality
- **Event-Driven Architecture**: Implements background tasks using discord.ext.tasks for periodic player status checks
- **Asynchronous Design**: Fully async/await pattern for non-blocking I/O operations with Discord API and Roblox API

## Data Persistence
- **JSON File Storage**: Uses local JSON file (data.json) for storing:
  - Tracked player configurations (Roblox user IDs)
  - Notification channel mappings (Discord channel IDs)
  - Ping role assignments (Discord role IDs for mentions)
- **In-Memory Cache**: Loads data into memory on startup for fast access, writes back to file on updates
- **Simple Data Model**: Three main collections (tracked_players, notification_channels, ping_roles)

**Rationale**: JSON file storage chosen for simplicity and ease of deployment. Suitable for small-to-medium scale tracking (dozens to hundreds of players). No database setup required, making it ideal for Replit deployment.

## Roblox Integration
- **Custom API Wrapper**: RobloxAPI class encapsulates all Roblox web API interactions
- **Session Management**: Persistent aiohttp.ClientSession for connection pooling and performance
- **API Endpoints Used**:
  - User info endpoint (users.roblox.com/v1/users)
  - Avatar thumbnails (thumbnails.roblox.com/v1/users/avatar)
  - Presence API (presence.roblox.com/v1/presence/users) for online status and game server info
  - Target game: The Strongest Battlegrounds (Place ID: 10449761463)
- **Server Link Detection**: Automatically detects if player has "Joins On" enabled and provides joinable server links

**Design Decision**: Separated Roblox API logic into dedicated module (roblox_api.py) for maintainability and potential reuse. Uses async HTTP client for non-blocking external API calls.

## Discord Bot Architecture
- **Command Tree Pattern**: Uses discord.app_commands.CommandTree for slash command registration
- **Intents Configuration**: 
  - message_content: For potential message-based interactions
  - guilds: For server-specific configurations
- **Slash Commands**: Modern Discord interaction model with ephemeral responses for error messages
- **Embed-Based UI**: Uses Discord embeds for formatted, visually appealing responses

## Background Monitoring System
- **Polling Strategy**: Periodic checks of player status every 30 seconds (tasks.loop decorator pattern)
- **Status Comparison**: Tracks previous state to detect changes (join/leave events)
- **Notification Pipeline**: Channels notifications to configured Discord channels with role pings
- **Message Editing**: Updates existing notification messages when player status changes (Online ✅ → Offline)
- **White Embed Format**: All notifications use white colored embeds (0xFFFFFF) with profile links, status, joins info, and server links

**Rationale**: Polling chosen over webhooks as Roblox doesn't provide real-time presence webhooks. Background tasks isolated from command handling for performance.

# External Dependencies

## Third-Party Services
- **Discord API**: Primary platform for bot operation
  - Slash commands (app_commands)
  - Message/embed sending
  - Channel and role management
- **Roblox Web APIs**: 
  - User profile data (users.roblox.com/v1/users)
  - Avatar thumbnails (thumbnails.roblox.com/v1/users/avatar)
  - Presence API (presence.roblox.com/v1/presence/users) for real-time online status and game server detection
  - Target game: The Strongest Battlegrounds (Place ID: 10449761463)

## Python Libraries
- **discord.py**: Discord bot framework with slash command support
- **aiohttp**: Async HTTP client for Roblox API requests
- **asyncio**: Async runtime for concurrent operations
- **json**: Data serialization/deserialization
- **datetime**: Timestamp handling for tracking

## Infrastructure Requirements
- **File System Access**: Read/write permissions for data.json persistence
- **Network Access**: Outbound HTTPS to Discord and Roblox APIs
- **Long-Running Process**: Bot requires continuous uptime for monitoring functionality
- **Environment Variables**: DISCORD_BOT_TOKEN (stored in Replit Secrets)

# Recent Changes

**October 7, 2025**: Initial bot implementation completed
- Created roblox_api.py with full Roblox API integration
- Implemented bot.py with all slash commands (/add-player, /list-tracked, /set-channel, /set-role)
- Added background tracking system that checks player status every 30 seconds
- Configured white embed notifications with profile links and server links
- Set up automatic message editing for status changes (Online ✅ ↔ Offline)
- Bot successfully deployed and running