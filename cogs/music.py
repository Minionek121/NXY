"""
Music cog — plays audio in a voice channel using yt-dlp + ffmpeg.

Requires: `pip install yt-dlp PyNaCl` and ffmpeg installed on the host
(apt install ffmpeg / brew install ffmpeg / add ffmpeg.exe to PATH on Windows).
This uses direct voice connections, not an external Lavalink node, so it's
simple to run but will use your bot host's CPU/bandwidth for transcoding.
"""
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import error_embed, success_embed

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streaming 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class GuildMusicState:
    def __init__(self):
        self.queue: list[dict] = []
        self.volume: float = 0.5
        self.loop: bool = False
        self.current: dict | None = None


class Music(commands.Cog):
    """Voice channel music playback with a per-guild queue."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.states: dict[int, GuildMusicState] = {}

    def _state(self, guild_id: int) -> GuildMusicState:
        return self.states.setdefault(guild_id, GuildMusicState())

    async def _resolve(self, query: str) -> dict:
        if yt_dlp is None:
            raise RuntimeError("yt-dlp isn't installed. Run: pip install yt-dlp")
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
        if "entries" in info:
            info = info["entries"][0]
        return {"title": info.get("title", "Unknown"), "url": info["url"], "webpage_url": info.get("webpage_url", query), "duration": info.get("duration", 0)}

    def _play_next(self, guild: discord.Guild):
        state = self._state(guild.id)
        vc = guild.voice_client
        if not vc:
            return
        if state.loop and state.current:
            state.queue.insert(0, state.current)
        if not state.queue:
            state.current = None
            return
        track = state.queue.pop(0)
        state.current = track
        source = discord.FFmpegPCMAudio(track["url"], **FFMPEG_OPTS)
        source = discord.PCMVolumeTransformer(source, volume=state.volume)
        vc.play(source, after=lambda e: self._play_next(guild))

    @app_commands.command(name="join", description="Join your current voice channel")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message(embed=error_embed("Join a voice channel first."), ephemeral=True)
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
        await interaction.response.send_message(embed=success_embed(f"Joined **{channel.name}**"))

    @app_commands.command(name="leave", description="Leave the voice channel")
    async def leave(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            self.states.pop(interaction.guild.id, None)
            await interaction.response.send_message(embed=success_embed("Left the voice channel."))
        else:
            await interaction.response.send_message(embed=error_embed("I'm not in a voice channel."), ephemeral=True)

    @app_commands.command(name="play", description="Play a song by URL or search query")
    @app_commands.describe(query="YouTube URL or search terms")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            return await interaction.response.send_message(embed=error_embed("Join a voice channel first."), ephemeral=True)
        await interaction.response.defer()

        if not interaction.guild.voice_client:
            await interaction.user.voice.channel.connect()

        try:
            track = await self._resolve(query)
        except Exception as e:
            return await interaction.followup.send(embed=error_embed(f"Couldn't find that: {e}"))

        state = self._state(interaction.guild.id)
        state.queue.append(track)

        if interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused():
            await interaction.followup.send(embed=success_embed(f"Queued **{track['title']}** (position {len(state.queue)})"))
        else:
            self._play_next(interaction.guild)
            await interaction.followup.send(embed=success_embed(f"Now playing **{track['title']}**"))

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message(embed=success_embed("Paused ⏸️"))
        else:
            await interaction.response.send_message(embed=error_embed("Nothing is playing."), ephemeral=True)

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message(embed=success_embed("Resumed ▶️"))
        else:
            await interaction.response.send_message(embed=error_embed("Nothing is paused."), ephemeral=True)

    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()  # triggers the `after` callback -> plays next
            await interaction.response.send_message(embed=success_embed("Skipped ⏭️"))
        else:
            await interaction.response.send_message(embed=error_embed("Nothing is playing."), ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        state = self._state(interaction.guild.id)
        state.queue.clear()
        state.current = None
        if vc:
            vc.stop()
        await interaction.response.send_message(embed=success_embed("Stopped and cleared the queue."))

    @app_commands.command(name="queue", description="Show the current music queue")
    async def queue_cmd(self, interaction: discord.Interaction):
        state = self._state(interaction.guild.id)
        if not state.current and not state.queue:
            return await interaction.response.send_message("The queue is empty.", ephemeral=True)
        lines = []
        if state.current:
            lines.append(f"▶️ **Now playing:** {state.current['title']}")
        for i, t in enumerate(state.queue, 1):
            lines.append(f"{i}. {t['title']}")
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="nowplaying", description="Show the currently playing song")
    async def nowplaying(self, interaction: discord.Interaction):
        state = self._state(interaction.guild.id)
        if not state.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        await interaction.response.send_message(f"▶️ **{state.current['title']}**\n{state.current['webpage_url']}")

    @app_commands.command(name="volume", description="Set playback volume (0-100)")
    @app_commands.describe(percent="Volume percentage")
    async def volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 100]):
        state = self._state(interaction.guild.id)
        state.volume = percent / 100
        vc = interaction.guild.voice_client
        if vc and vc.source:
            vc.source.volume = state.volume
        await interaction.response.send_message(embed=success_embed(f"Volume set to {percent}%"))

    @app_commands.command(name="loop", description="Toggle looping the current song")
    async def loop(self, interaction: discord.Interaction):
        state = self._state(interaction.guild.id)
        state.loop = not state.loop
        await interaction.response.send_message(embed=success_embed(f"Loop {'enabled 🔁' if state.loop else 'disabled'}"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
