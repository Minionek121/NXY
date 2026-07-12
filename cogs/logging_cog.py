import discord
from discord import app_commands
from discord.ext import commands

from utils.database import JSONStore
from utils.checks import is_admin, success_embed, error_embed
import config

log_config_db = JSONStore("log_config")  # {guild_id: {"channel_id": int, "events": {...}}}


class LoggingCog(commands.Cog, name="Logging"):
    """Server event logging: message edits/deletes, joins/leaves, bans."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_settings(self, guild_id: int) -> dict:
        settings = log_config_db.get(guild_id)
        if not settings:
            settings = {"channel_id": None, "events": dict(config.LOG_EVENTS_DEFAULT)}
        return settings

    async def _log(self, guild: discord.Guild, event: str, embed: discord.Embed):
        settings = self._get_settings(guild.id)
        if not settings["channel_id"] or not settings["events"].get(event, False):
            return
        channel = guild.get_channel(settings["channel_id"])
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    @app_commands.command(name="setup_logging", description="Set the channel used for event logs (Admin only)")
    @app_commands.describe(channel="Channel to send logs to")
    @is_admin()
    async def setup_logging(self, interaction: discord.Interaction, channel: discord.TextChannel):
        settings = self._get_settings(interaction.guild.id)
        settings["channel_id"] = channel.id
        log_config_db.set(interaction.guild.id, settings)
        await interaction.response.send_message(embed=success_embed(f"Logs will now be sent to {channel.mention}"))

    @app_commands.command(name="toggle_log", description="Enable or disable a specific log event type (Admin only)")
    @app_commands.describe(event="Event type to toggle")
    @app_commands.choices(event=[app_commands.Choice(name=e, value=e) for e in config.LOG_EVENTS_DEFAULT])
    @is_admin()
    async def toggle_log(self, interaction: discord.Interaction, event: app_commands.Choice[str]):
        settings = self._get_settings(interaction.guild.id)
        settings["events"][event.value] = not settings["events"].get(event.value, False)
        log_config_db.set(interaction.guild.id, settings)
        state = "enabled" if settings["events"][event.value] else "disabled"
        await interaction.response.send_message(embed=success_embed(f"`{event.value}` logging {state}."))

    @app_commands.command(name="disable_logging", description="Disable all event logging for this server (Admin only)")
    @is_admin()
    async def disable_logging(self, interaction: discord.Interaction):
        settings = self._get_settings(interaction.guild.id)
        settings["channel_id"] = None
        log_config_db.set(interaction.guild.id, settings)
        await interaction.response.send_message(embed=success_embed("Logging disabled for this server."))

    @app_commands.command(name="log_status", description="View current logging configuration")
    async def log_status(self, interaction: discord.Interaction):
        settings = self._get_settings(interaction.guild.id)
        channel = interaction.guild.get_channel(settings["channel_id"]) if settings["channel_id"] else None
        embed = discord.Embed(title="Logging Configuration", color=discord.Color.blurple())
        embed.add_field(name="Log channel", value=channel.mention if channel else "Not set", inline=False)
        for event, enabled in settings["events"].items():
            embed.add_field(name=event, value="✅" if enabled else "❌")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- Listeners ----------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = discord.Embed(title="🗑️ Message Deleted", color=discord.Color.red())
        embed.add_field(name="Author", value=str(message.author), inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Content", value=message.content[:1000] or "*(no text content)*", inline=False)
        await self._log(message.guild, "message_delete", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(title="✏️ Message Edited", color=discord.Color.orange())
        embed.add_field(name="Author", value=str(before.author), inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=before.content[:500] or "*(empty)*", inline=False)
        embed.add_field(name="After", value=after.content[:500] or "*(empty)*", inline=False)
        await self._log(before.guild, "message_edit", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(title="📥 Member Joined", description=f"{member.mention} ({member})", color=discord.Color.green())
        embed.add_field(name="Account created", value=discord.utils.format_dt(member.created_at, "R"))
        await self._log(member.guild, "member_join", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(title="📤 Member Left", description=f"{member} ({member.id})", color=discord.Color.dark_orange())
        await self._log(member.guild, "member_leave", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="🔨 Member Banned", description=f"{user} ({user.id})", color=discord.Color.red())
        await self._log(guild, "member_ban", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="🔓 Member Unbanned", description=f"{user} ({user.id})", color=discord.Color.green())
        await self._log(guild, "member_unban", embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return
        if after.channel and not before.channel:
            desc = f"{member.mention} joined **{after.channel.name}**"
        elif before.channel and not after.channel:
            desc = f"{member.mention} left **{before.channel.name}**"
        else:
            desc = f"{member.mention} moved from **{before.channel.name}** to **{after.channel.name}**"
        embed = discord.Embed(title="🔊 Voice State Update", description=desc, color=discord.Color.blurple())
        await self._log(member.guild, "voice_state", embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
