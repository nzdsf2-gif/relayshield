#!/bin/sh
# Thin wrapper kept because CLAUDE.md, the drift-check comments and the
# founder's shell history all name this path. The check itself is generic now:
# a sixth handler turned up in no deploy map on 2026-09-03 and needed exactly
# the same three questions asked of it.
#
#   sh tools/discord_bot_drift.sh
exec sh "$(dirname "$0")/handler_drift.sh" relayshield_discord_bot.py relayshield-discord-bot
