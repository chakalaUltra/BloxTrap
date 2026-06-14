# BloxTrap - Roblox Player Tracker Discord Bot

Advanced Discord bot for tracking Roblox players' online status with rich notifications and join buttons.

## Features
- Track multiple Roblox players per server
- Real-time online/offline notifications
- Direct "Join Server" buttons
- Beautiful embeds with avatars
- MongoDB persistence
- Efficient batch checking
- Web health check for Replit/Uptime

## Setup
1. Add bot to your Discord server with proper intents.
2. Set environment variables: `TOKEN`, `DATABASE` (MongoDB URI)
3. Run `python bot.py`

## Commands
- `/add-player <roblox_id>`
- `/list-tracked`
- `/set-channel <channel>`
- `/set-role <role>`

Improved by Grok for better performance, design, and reliability!