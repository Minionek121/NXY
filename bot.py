"""
All-in-one Discord bot: tickets, giveaways, moderation, economy + quizzes.

SETUP
1. pip install -r requirements.txt   (discord.py, python-dotenv, aiosqlite)
2. Copy .env.example to .env and fill in BOT_TOKEN / STAFF_ROLE_IDS / etc.
3. python bot.py

Data is stored locally in a SQLite file called bot.db, created automatically
next to this script the first time you run it. Back that file up if you
care about keeping economy/ticket/warning history.
"""

import os
import re
import time
import random
import asyncio
import logging
import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
import aiosqlite
import yt_dlp

# =========================================================================
# CONFIG
# =========================================================================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

_staff_raw = os.getenv("STAFF_ROLE_IDS", "")
STAFF_ROLE_IDS = [int(x) for x in _staff_raw.split(",") if x.strip().isdigit()]

_ticket_cat = os.getenv("TICKET_CATEGORY_ID", "")
TICKET_CATEGORY_ID = int(_ticket_cat) if _ticket_cat.isdigit() else None

_log_chan = os.getenv("LOG_CHANNEL_ID", "")
LOG_CHANNEL_ID = int(_log_chan) if _log_chan.isdigit() else None

# Only this user can run /addcoins and /removecoins, regardless of staff roles
_owner_raw = os.getenv("OWNER_USER_ID", "1482743052903649361")
OWNER_USER_ID = int(_owner_raw) if _owner_raw.isdigit() else None

CURRENCY_NAME = "coins"
CURRENCY_EMOJI = "🪙"

# ---- Economy tuning (your numbers) ----
# Chat rewards scale with message length: short messages earn the minimum,
# long ones scale up toward the max. Cooldown stops spam-farming.
CHAT_REWARD_MIN = 800_000
CHAT_REWARD_MAX = 1_200_000
CHAT_REWARD_LONG_MSG_CHARS = 150      # a message this long or more earns the max
CHAT_REWARD_COOLDOWN_SECONDS = 0

DAILY_REWARD_MIN = 5_000_000
DAILY_REWARD_MAX = 10_000_000

TICKET_TYPES = {
    "general": {"label": "General Support", "emoji": "🎫"},
    "premium": {"label": "Premium Support", "emoji": "💎"},
    "billing": {"label": "Billing / Purchases", "emoji": "💳"},
    "report": {"label": "Report a User", "emoji": "🚨"},
}

# ---- Music ----
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True

DB_PATH = "bot.db"


def fmt(n: int) -> str:
    """Pretty-print big numbers like 25000000 -> 25,000,000"""
    return f"{n:,}"


def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        role_ids = {r.id for r in interaction.user.roles}
        if role_ids.intersection(STAFF_ROLE_IDS):
            return True
        raise app_commands.CheckFailure("You don't have permission to do that.")
    return app_commands.check(predicate)


def is_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == OWNER_USER_ID:
            return True
        raise app_commands.CheckFailure("Only the bot owner can use this command.")
    return app_commands.check(predicate)


def parse_duration(text: str) -> int | None:
    match = re.fullmatch(r"(\d+)\s*([smhd])", text.strip().lower())
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return amount * multiplier


# =========================================================================
# DATABASE
# =========================================================================
class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS economy (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                last_daily REAL NOT NULL DEFAULT 0,
                last_chat_reward REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                ticket_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at REAL NOT NULL,
                claimed_by INTEGER
            );
            CREATE TABLE IF NOT EXISTS giveaways (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                host_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winners_count INTEGER NOT NULL,
                end_time REAL NOT NULL,
                ended INTEGER NOT NULL DEFAULT 0,
                required_role_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS giveaway_entries (
                message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (message_id, user_id)
            );
            """
        )
        await self.conn.commit()

    # ---- Economy ----
    async def get_balance(self, user_id: int) -> int:
        cur = await self.conn.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row is None:
            await self.conn.execute("INSERT INTO economy (user_id) VALUES (?)", (user_id,))
            await self.conn.commit()
            return 0
        return row[0]

    async def add_balance(self, user_id: int, amount: int):
        await self.get_balance(user_id)
        await self.conn.execute("UPDATE economy SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await self.conn.commit()

    async def transfer_balance(self, from_id: int, to_id: int, amount: int) -> bool:
        bal = await self.get_balance(from_id)
        if bal < amount:
            return False
        await self.add_balance(from_id, -amount)
        await self.add_balance(to_id, amount)
        return True

    async def get_last_chat_reward(self, user_id: int) -> float:
        await self.get_balance(user_id)
        cur = await self.conn.execute("SELECT last_chat_reward FROM economy WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0

    async def set_last_chat_reward(self, user_id: int, ts: float):
        await self.conn.execute("UPDATE economy SET last_chat_reward = ? WHERE user_id = ?", (ts, user_id))
        await self.conn.commit()

    async def get_last_daily(self, user_id: int) -> float:
        await self.get_balance(user_id)
        cur = await self.conn.execute("SELECT last_daily FROM economy WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0

    async def set_last_daily(self, user_id: int, ts: float):
        await self.conn.execute("UPDATE economy SET last_daily = ? WHERE user_id = ?", (ts, user_id))
        await self.conn.commit()

    async def get_leaderboard(self, limit: int = 10):
        cur = await self.conn.execute("SELECT user_id, balance FROM economy ORDER BY balance DESC LIMIT ?", (limit,))
        return await cur.fetchall()

    # ---- Warnings ----
    async def add_warning(self, user_id, guild_id, moderator_id, reason):
        await self.conn.execute(
            "INSERT INTO warnings (user_id, guild_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, guild_id, moderator_id, reason, time.time()),
        )
        await self.conn.commit()

    async def get_warnings(self, user_id, guild_id):
        cur = await self.conn.execute(
            "SELECT id, moderator_id, reason FROM warnings WHERE user_id = ? AND guild_id = ? ORDER BY created_at DESC",
            (user_id, guild_id),
        )
        return await cur.fetchall()

    async def clear_warnings(self, user_id, guild_id):
        await self.conn.execute("DELETE FROM warnings WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        await self.conn.commit()

    # ---- Tickets ----
    async def create_ticket(self, channel_id, guild_id, user_id, ticket_type):
        await self.conn.execute(
            "INSERT INTO tickets (channel_id, guild_id, user_id, ticket_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (channel_id, guild_id, user_id, ticket_type, time.time()),
        )
        await self.conn.commit()

    async def get_ticket(self, channel_id):
        cur = await self.conn.execute(
            "SELECT channel_id, guild_id, user_id, ticket_type, status, created_at, claimed_by FROM tickets WHERE channel_id = ?",
            (channel_id,),
        )
        return await cur.fetchone()

    async def close_ticket(self, channel_id):
        await self.conn.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (channel_id,))
        await self.conn.commit()

    async def claim_ticket(self, channel_id, staff_id):
        await self.conn.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (staff_id, channel_id))
        await self.conn.commit()

    async def count_open_tickets(self, guild_id, user_id) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    # ---- Giveaways ----
    async def create_giveaway(self, message_id, channel_id, guild_id, host_id, prize, winners_count, end_time, required_role_id=None):
        await self.conn.execute(
            "INSERT INTO giveaways (message_id, channel_id, guild_id, host_id, prize, winners_count, end_time, required_role_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, channel_id, guild_id, host_id, prize, winners_count, end_time, required_role_id),
        )
        await self.conn.commit()

    async def add_entry(self, message_id, user_id) -> bool:
        try:
            await self.conn.execute("INSERT INTO giveaway_entries (message_id, user_id) VALUES (?, ?)", (message_id, user_id))
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_entry(self, message_id, user_id):
        await self.conn.execute("DELETE FROM giveaway_entries WHERE message_id = ? AND user_id = ?", (message_id, user_id))
        await self.conn.commit()

    async def has_entered(self, message_id, user_id) -> bool:
        cur = await self.conn.execute("SELECT 1 FROM giveaway_entries WHERE message_id = ? AND user_id = ?", (message_id, user_id))
        return (await cur.fetchone()) is not None

    async def get_entries(self, message_id):
        cur = await self.conn.execute("SELECT user_id FROM giveaway_entries WHERE message_id = ?", (message_id,))
        return [r[0] for r in await cur.fetchall()]

    async def get_entry_count(self, message_id) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) FROM giveaway_entries WHERE message_id = ?", (message_id,))
        row = await cur.fetchone()
        return row[0] if row else 0

    async def get_giveaway(self, message_id):
        cur = await self.conn.execute(
            "SELECT message_id, channel_id, guild_id, host_id, prize, winners_count, end_time, ended, required_role_id FROM giveaways WHERE message_id = ?",
            (message_id,),
        )
        return await cur.fetchone()

    async def get_active_giveaways(self):
        cur = await self.conn.execute(
            "SELECT message_id, channel_id, guild_id, host_id, prize, winners_count, end_time, ended, required_role_id FROM giveaways WHERE ended = 0"
        )
        return await cur.fetchall()

    async def end_giveaway(self, message_id):
        await self.conn.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,))
        await self.conn.commit()


# =========================================================================
# TICKET UI
# =========================================================================
class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=v["label"], value=k, emoji=v["emoji"]) for k, v in TICKET_TYPES.items()]
        super().__init__(placeholder="Select a ticket category...", options=options, custom_id="ticket_type_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.client.open_ticket(interaction, self.values[0])


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.blurple, custom_id="ticket_claim", emoji="🙋")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.client.claim_ticket(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="ticket_close", emoji="🔒")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.client.close_ticket(interaction)


# =========================================================================
# GIVEAWAY UI
# =========================================================================
class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green, emoji="🎉", custom_id="gw_enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.client.toggle_entry(interaction)


# =========================================================================
# BOT
# =========================================================================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS, help_command=None)
        self.db = Database()
        self.last_active_channel: dict[int, int] = {}  # guild_id -> channel_id
        self.afk_users: dict[int, dict] = {}  # user_id -> {"reason": str, "since": float}
        self.music_queues: dict[int, list[dict]] = {}  # guild_id -> [{"title","url","stream_url","requester"}]

    async def setup_hook(self):
        await self.db.connect()
        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())
        self.add_view(GiveawayView())
        self.giveaway_checker.start()
        await self.tree.sync()
        log.info("Slash commands synced.")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="/ticket-panel | /gw-start"))

    async def on_message(self, message: discord.Message):
        await self.process_commands(message)
        if message.author.bot or not message.guild:
            return

        self.last_active_channel[message.guild.id] = message.channel.id

        # ---- AFK: clear the sender's AFK status if they had one ----
        if message.author.id in self.afk_users:
            del self.afk_users[message.author.id]
            try:
                await message.channel.send(f"👋 Welcome back {message.author.mention}, I've removed your AFK.", delete_after=10)
            except discord.Forbidden:
                pass

        # ---- AFK: notify if someone pinged an AFK user ----
        for mentioned in message.mentions:
            if mentioned.id in self.afk_users:
                info = self.afk_users[mentioned.id]
                since = int(info["since"])
                await message.channel.send(
                    f"💤 {mentioned.mention} is AFK: {info['reason']} (since <t:{since}:R>)"
                )

        now = time.time()
        last = await self.db.get_last_chat_reward(message.author.id)
        if now - last >= CHAT_REWARD_COOLDOWN_SECONDS:
            length_ratio = min(1.0, len(message.content) / CHAT_REWARD_LONG_MSG_CHARS)
            amount = int(CHAT_REWARD_MIN + (CHAT_REWARD_MAX - CHAT_REWARD_MIN) * length_ratio)
            await self.db.add_balance(message.author.id, amount)
            await self.db.set_last_chat_reward(message.author.id, now)

    # ---------------- Ticket logic ----------------
    async def open_ticket(self, interaction: discord.Interaction, ticket_type: str):
        guild, user = interaction.guild, interaction.user

        # Defer immediately — channel creation can take a moment and Discord
        # only gives us 3 seconds to acknowledge the interaction.
        await interaction.response.defer(ephemeral=True)

        if await self.db.count_open_tickets(guild.id, user.id) >= 2:
            await interaction.followup.send("❌ You already have open tickets. Close them before opening a new one.", ephemeral=True)
            return

        if not guild.me.guild_permissions.manage_channels:
            await interaction.followup.send(
                "❌ I don't have the **Manage Channels** permission, so I can't create ticket channels. "
                "Ask an admin to grant it to my role in Server Settings → Roles.",
                ephemeral=True,
            )
            return

        category = None
        if TICKET_CATEGORY_ID:
            category = guild.get_channel(TICKET_CATEGORY_ID)
            if category is None:
                await interaction.followup.send(
                    "⚠️ TICKET_CATEGORY_ID in your .env doesn't match a real category in this server "
                    "(or the bot can't see it). Creating the ticket without a category instead — "
                    "double check that ID or leave it blank.",
                    ephemeral=True,
                )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for role_id in STAFF_ROLE_IDS:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        type_info = TICKET_TYPES.get(ticket_type, {"label": ticket_type, "emoji": "🎫"})
        channel_name = f"ticket-{user.name}".lower().replace(" ", "-")[:90]

        try:
            channel = await guild.create_text_channel(
                name=channel_name, category=category, overwrites=overwrites,
                topic=f"Ticket for {user} | type: {ticket_type}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Discord blocked me from creating that channel — my role likely needs **Manage Channels** "
                "permission, or my role needs to be moved higher in Server Settings → Roles.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Discord rejected the channel creation: {e}", ephemeral=True)
            return

        await self.db.create_ticket(channel.id, guild.id, user.id, ticket_type)

        embed = discord.Embed(
            title=f"{type_info['emoji']} {type_info['label']}",
            description=f"Welcome {user.mention}! A staff member will be with you shortly.\n\nPlease describe your issue in detail.",
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Ticket owner: {user}")
        await channel.send(content=user.mention, embed=embed, view=TicketControlView())
        await interaction.followup.send(f"✅ Your ticket has been created: {channel.mention}", ephemeral=True)

    async def claim_ticket(self, interaction: discord.Interaction):
        role_ids = {r.id for r in interaction.user.roles}
        if not (interaction.user.guild_permissions.administrator or role_ids.intersection(STAFF_ROLE_IDS)):
            await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True)
            return
        ticket = await self.db.get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True)
            return
        await self.db.claim_ticket(interaction.channel.id, interaction.user.id)
        await interaction.response.send_message(embed=discord.Embed(
            description=f"🙋 This ticket has been claimed by {interaction.user.mention}.", color=discord.Color.blurple()
        ))

    async def close_ticket(self, interaction: discord.Interaction):
        ticket = await self.db.get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True)
            return
        role_ids = {r.id for r in interaction.user.roles}
        is_owner = interaction.user.id == ticket[2]
        is_staff_member = interaction.user.guild_permissions.administrator or role_ids.intersection(STAFF_ROLE_IDS)
        if not (is_owner or is_staff_member):
            await interaction.response.send_message("You can't close this ticket.", ephemeral=True)
            return
        await self.db.close_ticket(interaction.channel.id)
        await interaction.response.send_message(embed=discord.Embed(description="🔒 This ticket will be closed in 5 seconds...", color=discord.Color.red()))
        if LOG_CHANNEL_ID:
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"🔒 Ticket `{interaction.channel.name}` closed by {interaction.user.mention} (owner: <@{ticket[2]}>)")
        await interaction.channel.edit(name=f"closed-{interaction.channel.name}"[:90])
        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")

    # ---------------- Giveaway logic ----------------
    def _gw_embed(self, prize, winners, end_time, host_id, entries, required_role_id):
        embed = discord.Embed(
            title=f"🎉 GIVEAWAY: {prize}",
            description=(
                f"Click **Enter Giveaway** below to participate!\n\n"
                f"🏆 Winners: **{winners}**\n"
                f"⏰ Ends: <t:{int(end_time)}:R> (<t:{int(end_time)}:f>)\n"
                f"👤 Hosted by: <@{host_id}>\n"
                f"👥 Entries: **{entries}**"
            ),
            color=discord.Color.fuchsia(),
        )
        if required_role_id:
            embed.add_field(name="Requirement", value=f"Must have <@&{required_role_id}>", inline=False)
        embed.set_footer(text="Good luck!")
        return embed

    async def toggle_entry(self, interaction: discord.Interaction):
        gw = await self.db.get_giveaway(interaction.message.id)
        if not gw or gw[7]:
            await interaction.response.send_message("This giveaway has ended.", ephemeral=True)
            return
        _, channel_id, guild_id, host_id, prize, winners_count, end_time, ended, required_role_id = gw

        if required_role_id:
            role = interaction.guild.get_role(required_role_id)
            if role and role not in interaction.user.roles:
                await interaction.response.send_message(f"❌ You need the {role.mention} role to enter.", ephemeral=True)
                return

        if await self.db.has_entered(interaction.message.id, interaction.user.id):
            await self.db.remove_entry(interaction.message.id, interaction.user.id)
            await interaction.response.send_message("❌ You left the giveaway.", ephemeral=True)
        else:
            await self.db.add_entry(interaction.message.id, interaction.user.id)
            await interaction.response.send_message("✅ You're entered! Good luck!", ephemeral=True)

        entry_count = await self.db.get_entry_count(interaction.message.id)
        await interaction.message.edit(embed=self._gw_embed(prize, winners_count, end_time, host_id, entry_count, required_role_id))

    async def finish_giveaway(self, gw_row):
        message_id, channel_id, guild_id, host_id, prize, winners_count, end_time, ended, required_role_id = gw_row
        await self.db.end_giveaway(message_id)
        guild = self.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            message = None

        entries = await self.db.get_entries(message_id)
        if not entries:
            result_text = "No one entered this giveaway. 😢"
            winners = []
        else:
            winners = random.sample(entries, min(winners_count, len(entries)))
            result_text = ", ".join(f"<@{w}>" for w in winners)

        final_embed = discord.Embed(
            title=f"🎉 GIVEAWAY ENDED: {prize}",
            description=f"🏆 Winner(s): {result_text}\n👤 Hosted by: <@{host_id}>",
            color=discord.Color.dark_gray(),
        )
        if message:
            await message.edit(embed=final_embed, view=None)
            await message.reply(f"🎉 Congratulations {result_text}! You won **{prize}**!" if winners else "No valid entries, no winner this time.")

    @tasks.loop(seconds=15)
    async def giveaway_checker(self):
        now = time.time()
        for gw in await self.db.get_active_giveaways():
            if gw[6] <= now:
                await self.finish_giveaway(gw)

    @giveaway_checker.before_loop
    async def before_giveaway_checker(self):
        await self.wait_until_ready()

    # ---------------- Music ----------------
    async def extract_track(self, query: str) -> dict | None:
        """Runs the blocking yt-dlp lookup in a background thread."""
        loop = asyncio.get_event_loop()

        def _extract():
            info = ytdl.extract_info(query, download=False)
            if "entries" in info:  # search result or playlist -> take first
                info = info["entries"][0]
            return info

        try:
            info = await loop.run_in_executor(None, _extract)
        except Exception as e:
            log.warning(f"yt-dlp extraction failed: {e}")
            return None

        return {
            "title": info.get("title", "Unknown title"),
            "webpage_url": info.get("webpage_url", query),
            "stream_url": info.get("url"),
            "duration": info.get("duration"),
        }

    async def play_next(self, guild: discord.Guild):
        queue = self.music_queues.get(guild.id, [])
        voice_client = guild.voice_client
        if not voice_client:
            return

        if not queue:
            return  # nothing left; stay connected until /leave or timeout elsewhere

        track = queue.pop(0)
        source = discord.FFmpegPCMAudio(track["stream_url"], **FFMPEG_OPTIONS)

        def _after(error):
            if error:
                log.warning(f"Playback error: {error}")
            fut = asyncio.run_coroutine_threadsafe(self.play_next(guild), self.loop)
            try:
                fut.result()
            except Exception as e:
                log.warning(f"Error advancing queue: {e}")

        voice_client.play(source, after=_after)
        text_channel_id = self.last_active_channel.get(guild.id)
        channel = self.get_channel(text_channel_id) if text_channel_id else None
        if channel:
            await channel.send(embed=discord.Embed(
                description=f"🎶 Now playing: **{track['title']}**",
                color=discord.Color.blurple(),
            ))


bot = MyBot()


# =========================================================================
# SLASH COMMANDS — Tickets
# =========================================================================
@bot.tree.command(name="ticket-panel", description="Post the ticket panel in this channel")
@app_commands.describe(title="Panel embed title", description="Panel embed description", color="Hex color like #5865F2 (optional)")
@is_staff()
async def ticket_panel(interaction: discord.Interaction, title: str = "🎫 Support Tickets",
                        description: str = "Select a category below to open a ticket with our team.", color: str | None = None):
    embed_color = discord.Color.blurple()
    if color:
        try:
            embed_color = discord.Color(int(color.lstrip("#"), 16))
        except ValueError:
            pass
    embed = discord.Embed(title=title, description=description, color=embed_color)
    types_text = "\n".join(f"{v['emoji']} **{v['label']}**" for v in TICKET_TYPES.values())
    embed.add_field(name="Categories", value=types_text, inline=False)
    embed.set_footer(text="Powered by your friendly neighborhood ticket bot")
    try:
        await interaction.response.send_message(embed=embed, view=TicketPanelView())
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I can't post here — I likely need **Send Messages** and **Embed Links** permission in this channel.",
            ephemeral=True,
        )


# =========================================================================
# SLASH COMMANDS — Giveaways
# =========================================================================
@bot.tree.command(name="gw-start", description="Start a fully customized giveaway")
@app_commands.describe(prize="What are you giving away?", duration="Duration like 30s, 10m, 2h, 1d",
                        winners="Number of winners", required_role="Role required to enter (optional)",
                        channel="Channel to post in (optional, defaults to here)")
@is_staff()
async def gw_start(interaction: discord.Interaction, prize: str, duration: str,
                    winners: app_commands.Range[int, 1, 20] = 1,
                    required_role: discord.Role | None = None, channel: discord.TextChannel | None = None):
    seconds = parse_duration(duration)
    if seconds is None or seconds < 5:
        await interaction.response.send_message("❌ Invalid duration. Use formats like `30s`, `10m`, `2h`, `1d`.", ephemeral=True)
        return
    target_channel = channel or interaction.channel
    end_time = time.time() + seconds
    embed = bot._gw_embed(prize, winners, end_time, interaction.user.id, 0, required_role.id if required_role else None)
    msg = await target_channel.send(embed=embed, view=GiveawayView())
    await bot.db.create_giveaway(msg.id, target_channel.id, interaction.guild.id, interaction.user.id, prize, winners, end_time, required_role.id if required_role else None)
    await interaction.response.send_message(f"✅ Giveaway started in {target_channel.mention}!", ephemeral=True)


@bot.tree.command(name="gw-end", description="End a giveaway early")
@app_commands.describe(message_id="The giveaway message ID")
@is_staff()
async def gw_end(interaction: discord.Interaction, message_id: str):
    try:
        mid = int(message_id)
    except ValueError:
        await interaction.response.send_message("Invalid message ID.", ephemeral=True)
        return
    gw = await bot.db.get_giveaway(mid)
    if not gw or gw[7]:
        await interaction.response.send_message("Giveaway not found or already ended.", ephemeral=True)
        return
    await interaction.response.send_message("Ending giveaway...", ephemeral=True)
    await bot.finish_giveaway(gw)


@bot.tree.command(name="gw-reroll", description="Reroll winners for an ended giveaway")
@app_commands.describe(message_id="The giveaway message ID")
@is_staff()
async def gw_reroll(interaction: discord.Interaction, message_id: str):
    try:
        mid = int(message_id)
    except ValueError:
        await interaction.response.send_message("Invalid message ID.", ephemeral=True)
        return
    gw = await bot.db.get_giveaway(mid)
    if not gw:
        await interaction.response.send_message("Giveaway not found.", ephemeral=True)
        return
    _, channel_id, guild_id, host_id, prize, winners_count, end_time, ended, required_role_id = gw
    entries = await bot.db.get_entries(mid)
    if not entries:
        await interaction.response.send_message("No entries to reroll from.", ephemeral=True)
        return
    new_winners = random.sample(entries, min(winners_count, len(entries)))
    channel = interaction.guild.get_channel(channel_id)
    mentions = ", ".join(f"<@{w}>" for w in new_winners)
    await channel.send(f"🔁 **Reroll!** New winner(s) for **{prize}**: {mentions}")
    await interaction.response.send_message("Rerolled!", ephemeral=True)


# =========================================================================
# SLASH COMMANDS — Economy
# =========================================================================
@bot.tree.command(name="balance", description="Check your or someone else's balance")
@app_commands.describe(user="Whose balance to check")
async def balance(interaction: discord.Interaction, user: discord.Member | None = None):
    target = user or interaction.user
    bal = await bot.db.get_balance(target.id)
    await interaction.response.send_message(embed=discord.Embed(
        description=f"💰 {target.mention} has **{fmt(bal)} {CURRENCY_NAME}** {CURRENCY_EMOJI}", color=discord.Color.blurple()
    ))


@bot.tree.command(name="daily", description="Claim your daily reward")
async def daily(interaction: discord.Interaction):
    now = time.time()
    last = await bot.db.get_last_daily(interaction.user.id)
    remaining = 86400 - (now - last)
    if remaining > 0:
        hours, minutes = int(remaining // 3600), int((remaining % 3600) // 60)
        await interaction.response.send_message(f"⏳ Already claimed. Try again in {hours}h {minutes}m.", ephemeral=True)
        return
    amount = random.randint(DAILY_REWARD_MIN, DAILY_REWARD_MAX)
    await bot.db.add_balance(interaction.user.id, amount)
    await bot.db.set_last_daily(interaction.user.id, now)
    await interaction.response.send_message(embed=discord.Embed(
        description=f"✅ You claimed **{fmt(amount)} {CURRENCY_NAME}** {CURRENCY_EMOJI}!", color=discord.Color.green()
    ))


@bot.tree.command(name="gift", description="Send some of your currency to another member")
@app_commands.describe(user="Who to send currency to", amount="How much to send")
async def gift(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, None]):
    if user.id == interaction.user.id:
        await interaction.response.send_message("You can't gift yourself.", ephemeral=True)
        return
    if user.bot:
        await interaction.response.send_message("You can't gift a bot.", ephemeral=True)
        return
    if not await bot.db.transfer_balance(interaction.user.id, user.id, amount):
        await interaction.response.send_message(f"❌ You don't have enough {CURRENCY_NAME}.", ephemeral=True)
        return
    await interaction.response.send_message(embed=discord.Embed(
        description=f"🎁 {interaction.user.mention} gifted **{fmt(amount)} {CURRENCY_NAME}** {CURRENCY_EMOJI} to {user.mention}!",
        color=discord.Color.pink(),
    ))


@bot.tree.command(name="leaderboard", description="See the richest members")
async def leaderboard(interaction: discord.Interaction):
    rows = await bot.db.get_leaderboard(10)
    if not rows:
        await interaction.response.send_message("No data yet.", ephemeral=True)
        return
    lines = [f"**{i}.** <@{uid}> — {fmt(bal)} {CURRENCY_NAME}" for i, (uid, bal) in enumerate(rows, start=1)]
    await interaction.response.send_message(embed=discord.Embed(
        title=f"🏆 {CURRENCY_NAME.title()} Leaderboard", description="\n".join(lines), color=discord.Color.gold()
    ))


@bot.tree.command(name="addcoins", description="Grant coins to a member (bot owner only)")
@app_commands.describe(user="Who to give coins to", amount="How much to grant", reason="Why (shown in the log)")
@is_owner()
async def addcoins(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, None], reason: str = "No reason provided"):
    await bot.db.add_balance(user.id, amount)
    new_balance = await bot.db.get_balance(user.id)
    await interaction.response.send_message(embed=discord.Embed(
        description=f"✅ Granted **{fmt(amount)} {CURRENCY_NAME}** {CURRENCY_EMOJI} to {user.mention}.\n"
                    f"New balance: **{fmt(new_balance)} {CURRENCY_NAME}**",
        color=discord.Color.green(),
    ))
    await _log_action(
        interaction.guild,
        f"💰 {interaction.user} granted {fmt(amount)} {CURRENCY_NAME} to {user} — {reason}",
    )


@bot.tree.command(name="removecoins", description="Remove coins from a member (bot owner only)")
@app_commands.describe(user="Who to remove coins from", amount="How much to remove", reason="Why (shown in the log)")
@is_owner()
async def removecoins(interaction: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, None], reason: str = "No reason provided"):
    await bot.db.add_balance(user.id, -amount)
    new_balance = await bot.db.get_balance(user.id)
    await interaction.response.send_message(embed=discord.Embed(
        description=f"✅ Removed **{fmt(amount)} {CURRENCY_NAME}** {CURRENCY_EMOJI} from {user.mention}.\n"
                    f"New balance: **{fmt(new_balance)} {CURRENCY_NAME}**",
        color=discord.Color.orange(),
    ))
    await _log_action(
        interaction.guild,
        f"💸 {interaction.user} removed {fmt(amount)} {CURRENCY_NAME} from {user} — {reason}",
    )


# =========================================================================
# SLASH COMMANDS — Moderation
# =========================================================================
async def _log_action(guild: discord.Guild, text: str):
    if LOG_CHANNEL_ID:
        channel = guild.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(text)


@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(member="Who to kick", reason="Reason")
@is_staff()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=f"{reason} | by {interaction.user}")
    await interaction.response.send_message(embed=discord.Embed(description=f"👢 {member.mention} was kicked.\n**Reason:** {reason}", color=discord.Color.orange()))
    await _log_action(interaction.guild, f"👢 {member} kicked by {interaction.user} — {reason}")


@bot.tree.command(name="ban", description="Ban a member")
@app_commands.describe(member="Who to ban", reason="Reason")
@is_staff()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.ban(reason=f"{reason} | by {interaction.user}")
    await interaction.response.send_message(embed=discord.Embed(description=f"🔨 {member.mention} was banned.\n**Reason:** {reason}", color=discord.Color.red()))
    await _log_action(interaction.guild, f"🔨 {member} banned by {interaction.user} — {reason}")


@bot.tree.command(name="unban", description="Unban a user by ID")
@app_commands.describe(user_id="The user ID to unban")
@is_staff()
async def unban(interaction: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.response.send_message(embed=discord.Embed(description=f"✅ {user.mention} was unbanned.", color=discord.Color.green()))
    except (ValueError, discord.NotFound):
        await interaction.response.send_message("❌ That user isn't banned or the ID is invalid.", ephemeral=True)


@bot.tree.command(name="timeout", description="Timeout (mute) a member")
@app_commands.describe(member="Who to timeout", minutes="Duration in minutes", reason="Reason")
@is_staff()
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "No reason provided"):
    until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
    await member.timeout(until, reason=f"{reason} | by {interaction.user}")
    await interaction.response.send_message(embed=discord.Embed(description=f"🔇 {member.mention} timed out for {minutes}m.\n**Reason:** {reason}", color=discord.Color.orange()))
    await _log_action(interaction.guild, f"🔇 {member} timed out {minutes}m by {interaction.user} — {reason}")


@bot.tree.command(name="untimeout", description="Remove a timeout from a member")
@app_commands.describe(member="Who to remove timeout from")
@is_staff()
async def untimeout_cmd(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None, reason=f"Timeout removed by {interaction.user}")
    await interaction.response.send_message(embed=discord.Embed(description=f"🔊 {member.mention}'s timeout removed.", color=discord.Color.green()))


@bot.tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Who to warn", reason="Reason")
@is_staff()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    await bot.db.add_warning(member.id, interaction.guild.id, interaction.user.id, reason)
    await interaction.response.send_message(embed=discord.Embed(description=f"⚠️ {member.mention} was warned.\n**Reason:** {reason}", color=discord.Color.yellow()))
    try:
        await member.send(f"⚠️ You were warned in **{interaction.guild.name}**: {reason}")
    except discord.Forbidden:
        pass


@bot.tree.command(name="warnings", description="View a member's warnings")
@app_commands.describe(member="Whose warnings to view")
@is_staff()
async def warnings_cmd(interaction: discord.Interaction, member: discord.Member):
    rows = await bot.db.get_warnings(member.id, interaction.guild.id)
    if not rows:
        await interaction.response.send_message(f"{member.mention} has no warnings.", ephemeral=True)
        return
    lines = [f"**#{r[0]}** by <@{r[1]}> — {r[2]}" for r in rows]
    await interaction.response.send_message(embed=discord.Embed(title=f"Warnings for {member}", description="\n".join(lines), color=discord.Color.yellow()))


@bot.tree.command(name="clearwarnings", description="Clear all warnings for a member")
@app_commands.describe(member="Whose warnings to clear")
@is_staff()
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    await bot.db.clear_warnings(member.id, interaction.guild.id)
    await interaction.response.send_message(f"✅ Cleared warnings for {member.mention}.")


@bot.tree.command(name="purge", description="Delete a number of recent messages")
@app_commands.describe(amount="How many messages to delete (max 100)")
@is_staff()
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)


@bot.tree.command(name="slowmode", description="Set slowmode for this channel")
@app_commands.describe(seconds="Slowmode delay in seconds (0 to disable)")
@is_staff()
async def slowmode(interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message("✅ Slowmode disabled." if seconds == 0 else f"✅ Slowmode set to {seconds}s.")


@bot.tree.command(name="lock", description="Lock this channel so @everyone can't send messages")
@is_staff()
async def lock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔒 Channel locked.")


@bot.tree.command(name="unlock", description="Unlock this channel")
@is_staff()
async def unlock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔓 Channel unlocked.")


@bot.tree.command(name="userinfo", description="Get info about a member")
@app_commands.describe(member="Whose info to view")
async def userinfo(interaction: discord.Interaction, member: discord.Member | None = None):
    target = member or interaction.user
    embed = discord.Embed(title=str(target), color=discord.Color.blurple())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Joined Server", value=discord.utils.format_dt(target.joined_at, "R") if target.joined_at else "Unknown")
    embed.add_field(name="Account Created", value=discord.utils.format_dt(target.created_at, "R"))
    embed.add_field(name="Roles", value=", ".join(r.mention for r in target.roles if r.name != "@everyone") or "None", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="serverinfo", description="Get info about this server")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Members", value=str(guild.member_count))
    embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "R"))
    embed.add_field(name="Owner", value=f"<@{guild.owner_id}>")
    embed.add_field(name="Roles", value=str(len(guild.roles)))
    embed.add_field(name="Channels", value=str(len(guild.channels)))
    await interaction.response.send_message(embed=embed)


# =========================================================================
# SLASH COMMANDS — Fun
# =========================================================================
@bot.tree.command(name="afk", description="Set yourself as AFK")
@app_commands.describe(reason="Why you're AFK (optional)")
async def afk(interaction: discord.Interaction, reason: str = "AFK"):
    bot.afk_users[interaction.user.id] = {"reason": reason, "since": time.time()}
    await interaction.response.send_message(f"💤 {interaction.user.mention} is now AFK: {reason}")


@bot.tree.command(name="roll", description="Roll a dice")
@app_commands.describe(sides="Number of sides on the dice (default 6)")
async def roll(interaction: discord.Interaction, sides: app_commands.Range[int, 2, 1000] = 6):
    result = random.randint(1, sides)
    await interaction.response.send_message(embed=discord.Embed(
        description=f"🎲 {interaction.user.mention} rolled a **d{sides}** and got **{result}**!",
        color=discord.Color.blurple(),
    ))


@bot.tree.command(name="flip", description="Flip a coin")
async def flip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    emoji = "🪙"
    await interaction.response.send_message(embed=discord.Embed(
        description=f"{emoji} The coin landed on **{result}**!", color=discord.Color.gold()
    ))


# =========================================================================
# SLASH COMMANDS — Casino (wager your coins)
# =========================================================================
@bot.tree.command(name="coinflip", description="Bet coins on a coin flip — double or nothing")
@app_commands.describe(bet="How much to wager", choice="Heads or Tails")
@app_commands.choices(choice=[
    app_commands.Choice(name="Heads", value="heads"),
    app_commands.Choice(name="Tails", value="tails"),
])
async def coinflip(interaction: discord.Interaction, bet: app_commands.Range[int, 1, None], choice: app_commands.Choice[str]):
    balance = await bot.db.get_balance(interaction.user.id)
    if balance < bet:
        await interaction.response.send_message(f"❌ You don't have {fmt(bet)} {CURRENCY_NAME}.", ephemeral=True)
        return

    result = random.choice(["heads", "tails"])
    if result == choice.value:
        await bot.db.add_balance(interaction.user.id, bet)
        await interaction.response.send_message(embed=discord.Embed(
            description=f"🪙 It landed on **{result.title()}** — you called it! You won **{fmt(bet)} {CURRENCY_NAME}** {CURRENCY_EMOJI}.",
            color=discord.Color.green(... (15 KB left)
