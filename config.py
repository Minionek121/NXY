"""
Central configuration. Values come from environment variables (a .env file
works via python-dotenv, loaded in main.py) so you never hardcode a token.
"""
import os

# --- Core ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_TOKEN_HERE")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0")) or None

# --- Embeds ---
EMBED_COLOR = 0x5865F2          # Discord blurple, used as the default embed color
EMBED_COLOR_SUCCESS = 0x57F287
EMBED_COLOR_ERROR = 0xED4245
EMBED_COLOR_WARN = 0xFEE75C

# --- Casino ---
STARTING_BALANCE = 500
DAILY_REWARD = 250
WORK_MIN, WORK_MAX = 50, 200
WORK_COOLDOWN_SECONDS = 60 * 60          # 1 hour
DAILY_COOLDOWN_SECONDS = 60 * 60 * 24    # 24 hours

# --- PS99 (Pet Simulator 99) ---
# Official Big Games public API (docs: github.com/BIG-Games-LLC/ps99-public-api-docs).
# No API key needed for the /v1/clans/* endpoints used here.
PS99_API_BASE = "https://ps99.biggamesapi.io"

# --- Logging cog ---
LOG_EVENTS_DEFAULT = {
    "message_delete": True,
    "message_edit": True,
    "member_join": True,
    "member_leave": True,
    "member_ban": True,
    "member_unban": True,
    "voice_state": False,
}
