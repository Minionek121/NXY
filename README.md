# Multi-Purpose Discord Bot

A modular Discord bot built with `discord.py` cogs — 101 slash commands across
12 categories. Each category is its own file under `cogs/`, so you can add,
remove, or hand off a category without touching the rest of the bot.

## Structure

```
discord_bot/
├── main.py                # Entry point — loads every cog, syncs slash commands
├── config.py               # All tunable settings (currency amounts, colors, API URLs)
├── requirements.txt
├── .env.example             # Copy to .env and fill in your token
├── utils/
│   ├── database.py         # Simple JSON key-value store shared by all cogs
│   └── checks.py            # Permission decorators (@is_admin, @is_mod, @is_bot_owner)
├── data/                   # Auto-created JSON files (economy, warnings, tickets, ...)
└── cogs/
    ├── moderation.py       # kick, ban, mute, warn, purge, lock/unlock, ...
    ├── afk.py               # AFK status + auto ping notifications
    ├── fun.py               # 8ball, dice, rps, trivia, riddles, ship, ...
    ├── utility.py           # userinfo, serverinfo, poll, remindme, calculator, ...
    ├── music.py             # Voice playback via yt-dlp (join/play/queue/skip/...)
    ├── logging_cog.py       # Configurable event logging (edits, deletes, joins, bans...)
    ├── admin.py             # Role management, announcements, bot owner tools
    ├── casino.py            # Virtual-currency economy: daily/work, slots, blackjack, roulette
    ├── tickets.py           # Button + modal support ticket system
    ├── giveaways.py         # Button-based giveaways with timed auto-draw
    ├── welcome.py           # Configurable welcome messages
    └── ps99.py              # Pet Simulator 99 clan/player/battle stats
```

## Setup

1. **Install dependencies**
   ```
   pip install -r requirements.txt --break-system-packages
   ```
   Music also needs `ffmpeg` installed on your system (`apt install ffmpeg`,
   `brew install ffmpeg`, or add `ffmpeg.exe` to PATH on Windows).

2. **Create a bot application** at https://discord.com/developers/applications,
   enable the **Server Members** and **Message Content** privileged intents
   under the Bot tab, and copy the token.

3. **Configure environment**
   ```
   cp .env.example .env
   ```
   Fill in `DISCORD_TOKEN` and `BOT_OWNER_ID` (your Discord user ID — right-click
   yourself with Developer Mode on, "Copy User ID"). The owner ID gates
   `/sync`, `/reload`, and `/shutdown`.

4. **Invite the bot** to your server with the `applications.commands` and
   `bot` scopes, and enough permissions for whichever categories you use
   (Administrator is simplest while testing).

5. **Run it**
   ```
   python main.py
   ```
   Slash commands sync automatically on startup — first sync can take up to
   an hour to propagate globally on Discord's side, but shows up instantly
   if you test in a single server via a guild-scoped sync (swap
   `bot.tree.sync()` for `bot.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))`
   while developing).

## Notes on specific cogs

- **Storage**: everything persists to flat JSON files in `data/` (economy
  balances, warnings, ticket counters, welcome config, log config). Fine for
  small-to-medium servers; swap `utils/database.py` for a real database if
  you need concurrent-write safety at scale — no cog code needs to change,
  they only call `get`/`set`/`update`.
- **Casino**: entirely virtual currency, scoped per-server, starts everyone
  at 500 coins. No real money or purchases involved anywhere.
- **Music**: connects directly to voice and transcodes with ffmpeg (no
  external Lavalink node needed), which is simple to run but uses your
  bot's own CPU/bandwidth. Fine for a handful of servers; for larger scale
  you'd eventually want a Lavalink-based rewrite.
- **PS99 stats**: uses Big Games' official public API
  (`ps99.biggamesapi.io`, docs at
  `github.com/BIG-Games-LLC/ps99-public-api-docs`), no key required. The
  clan/player endpoints are a **sample of the top 25 clans by all-time
  battle points** — a clan or player not showing up doesn't mean they don't
  exist, just that they're outside that sample window.
- **Giveaways**: state is in-memory, so active giveaways don't survive a bot
  restart. Move `Giveaways.active` into the JSON store if you need that.
- **Tickets/Welcome/Giveaways** were migrated from your original single-file
  bot but rewritten to store settings **per-guild** instead of in global
  variables — the original would have mixed up ticket categories and
  welcome messages across different servers if installed on more than one.
