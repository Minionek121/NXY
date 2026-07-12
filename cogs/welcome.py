import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from utils.database import JSONStore
from utils.checks import is_admin, success_embed, error_embed

welcome_db = JSONStore("welcome")  # {guild_id: {channel_id, message}}


def _render(message: str, member: discord.Member) -> str:
    return (
        message.replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count))
    )


class Welcome(commands.Cog):
    """Configurable welcome messages sent when a new member joins."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="welcome_setup", description="Set up the welcome message system (Admin only)")
    @app_commands.describe(channel="Channel for welcome messages", message="Use {user}, {username}, {server}, {count}")
    @is_admin()
    async def welcome_setup(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        welcome_db.set(interaction.guild.id, {"channel_id": channel.id, "message": message})

        embed = discord.Embed(description=_render(message, interaction.user), color=discord.Color.green(), timestamp=datetime.now())
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"Member #{interaction.guild.member_count}")
        await channel.send(embed=embed)

        await interaction.response.send_message(embed=success_embed(f"Welcome messages will be sent to {channel.mention}"), ephemeral=True)

    @app_commands.command(name="welcome_disable", description="Disable welcome messages (Admin only)")
    @is_admin()
    async def welcome_disable(self, interaction: discord.Interaction):
        welcome_db.delete(interaction.guild.id)
        await interaction.response.send_message(embed=success_embed("Welcome messages disabled."), ephemeral=True)

    @app_commands.command(name="welcome_test", description="Send a test welcome message (Admin only)")
    @is_admin()
    async def welcome_test(self, interaction: discord.Interaction):
        cfg = welcome_db.get(interaction.guild.id)
        if not cfg:
            return await interaction.response.send_message(embed=error_embed("Welcome system not set up! Use /welcome_setup first."), ephemeral=True)
        channel = interaction.guild.get_channel(cfg["channel_id"])
        if not channel:
            return await interaction.response.send_message(embed=error_embed("Welcome channel not found."), ephemeral=True)

        embed = discord.Embed(description=_render(cfg["message"], interaction.user), color=discord.Color.green(), timestamp=datetime.now())
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"TEST MESSAGE — Member #{interaction.guild.member_count}")
        await channel.send(embed=embed)
        await interaction.response.send_message(embed=success_embed("Test welcome message sent!"), ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = welcome_db.get(member.guild.id)
        if not cfg:
            return
        channel = member.guild.get_channel(cfg["channel_id"])
        if not channel:
            return
        embed = discord.Embed(description=_render(cfg["message"], member), color=discord.Color.green(), timestamp=datetime.now())
        embed.set_author(name=member.name, icon_url=member.display_avatar.url)
        embed.set_footer(text=f"Member #{member.guild.member_count}")
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
