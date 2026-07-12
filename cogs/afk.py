import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from utils.database import JSONStore
from utils.checks import success_embed

afk_db = JSONStore("afk")  # {guild_id: {user_id: {reason, timestamp}}}


class AFK(commands.Cog):
    """AFK status: set a status, get auto-notified pings while away, auto-clear on return."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="afk", description="Set yourself as AFK with an optional reason")
    @app_commands.describe(reason="Why you're AFK")
    async def afk(self, interaction: discord.Interaction, reason: str = "AFK"):
        data = afk_db.get(interaction.guild.id, {})
        data[str(interaction.user.id)] = {"reason": reason, "timestamp": datetime.utcnow().isoformat()}
        afk_db.set(interaction.guild.id, data)
        await interaction.response.send_message(embed=success_embed(f"You're now AFK: {reason}"))

    @app_commands.command(name="afk_list", description="List all AFK members in this server")
    async def afk_list(self, interaction: discord.Interaction):
        data = afk_db.get(interaction.guild.id, {})
        if not data:
            return await interaction.response.send_message("No one is AFK right now.", ephemeral=True)
        embed = discord.Embed(title="Currently AFK", color=discord.Color.blurple())
        for uid, info in data.items():
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"Unknown ({uid})"
            embed.add_field(name=name, value=info["reason"], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="afk_clear", description="Manually clear your own AFK status")
    async def afk_clear(self, interaction: discord.Interaction):
        data = afk_db.get(interaction.guild.id, {})
        if data.pop(str(interaction.user.id), None) is not None:
            afk_db.set(interaction.guild.id, data)
            await interaction.response.send_message(embed=success_embed("AFK status cleared."), ephemeral=True)
        else:
            await interaction.response.send_message("You weren't AFK.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        data = afk_db.get(message.guild.id, {})
        changed = False

        # Returning user: clear their AFK
        if str(message.author.id) in data:
            data.pop(str(message.author.id))
            changed = True
            try:
                await message.channel.send(f"👋 Welcome back, {message.author.mention} — I removed your AFK status.", delete_after=8)
            except discord.Forbidden:
                pass

        # Pinged users who are AFK: notify the pinger
        if message.mentions:
            for mentioned in message.mentions:
                info = data.get(str(mentioned.id))
                if info:
                    ts = int(datetime.fromisoformat(info["timestamp"]).timestamp())
                    try:
                        await message.channel.send(f"💤 {mentioned.display_name} is AFK: {info['reason']} (since <t:{ts}:R>)", delete_after=10)
                    except discord.Forbidden:
                        pass

        if changed:
            afk_db.set(message.guild.id, data)


async def setup(bot: commands.Bot):
    await bot.add_cog(AFK(bot))
