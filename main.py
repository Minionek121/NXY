import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

import config

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bot")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents, help_command=None)

COGS = [
    "cogs.moderation",
    "cogs.afk",
    "cogs.fun",
    "cogs.utility",
    "cogs.music",
    "cogs.logging_cog",
    "cogs.admin",
    "cogs.casino",
    "cogs.tickets",
    "cogs.giveaways",
    "cogs.welcome",
    "cogs.ps99",
]


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    log.info(f"In {len(bot.guilds)} server(s)")
    try:
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} slash command(s)")
    except discord.HTTPException as e:
        log.error(f"Failed to sync commands: {e}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    log.error(f"Prefix command error: {error}")


async def load_all_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            log.info(f"Loaded {cog}")
        except Exception as e:
            log.error(f"Failed to load {cog}: {e}")


async def main():
    async with bot:
        await load_all_cogs()
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    if config.DISCORD_TOKEN == "YOUR_TOKEN_HERE":
        print("⚠️  Set DISCORD_TOKEN in your .env file before running the bot.")
    else:
        asyncio.run(main())
