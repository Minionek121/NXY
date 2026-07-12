import discord
from discord import app_commands
from discord.ext import commands
import time
import platform

from utils.checks import is_admin, is_bot_owner, success_embed, error_embed

START_TIME = time.time()


class Admin(commands.Cog):
    """Server administration and bot-owner utilities."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="addrole", description="Add a role to a member (Admin only)")
    @is_admin()
    async def addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await member.add_roles(role, reason=f"Added by {interaction.user}")
        await interaction.response.send_message(embed=success_embed(f"Added **{role.name}** to **{member}**"))

    @app_commands.command(name="removerole", description="Remove a role from a member (Admin only)")
    @is_admin()
    async def removerole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await member.remove_roles(role, reason=f"Removed by {interaction.user}")
        await interaction.response.send_message(embed=success_embed(f"Removed **{role.name}** from **{member}**"))

    @app_commands.command(name="createrole", description="Create a new role (Admin only)")
    @app_commands.describe(name="Role name", color="Hex color, e.g. #5865F2")
    @is_admin()
    async def createrole(self, interaction: discord.Interaction, name: str, color: str = "#99AAB5"):
        try:
            colour = discord.Colour(int(color.lstrip("#"), 16))
        except ValueError:
            return await interaction.response.send_message(embed=error_embed("Invalid hex color."), ephemeral=True)
        role = await interaction.guild.create_role(name=name, colour=colour, reason=f"Created by {interaction.user}")
        await interaction.response.send_message(embed=success_embed(f"Created role {role.mention}"))

    @app_commands.command(name="deleterole", description="Delete a role (Admin only)")
    @is_admin()
    async def deleterole(self, interaction: discord.Interaction, role: discord.Role):
        name = role.name
        await role.delete(reason=f"Deleted by {interaction.user}")
        await interaction.response.send_message(embed=success_embed(f"Deleted role **{name}**"))

    @app_commands.command(name="announce", description="Send an announcement embed to a channel (Admin only)")
    @app_commands.describe(channel="Channel to post in", message="Announcement text")
    @is_admin()
    async def announce(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        embed = discord.Embed(title="📢 Announcement", description=message, color=discord.Color.gold())
        embed.set_footer(text=f"Posted by {interaction.user}")
        await channel.send(embed=embed)
        await interaction.response.send_message(embed=success_embed(f"Announcement posted in {channel.mention}"), ephemeral=True)

    @app_commands.command(name="servericon", description="Change the server icon by image URL (Admin only)")
    @is_admin()
    async def servericon(self, interaction: discord.Interaction, image_url: str):
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return await interaction.response.send_message(embed=error_embed("Couldn't fetch that image."), ephemeral=True)
                data = await resp.read()
        await interaction.guild.edit(icon=data, reason=f"Changed by {interaction.user}")
        await interaction.response.send_message(embed=success_embed("Server icon updated."))

    @app_commands.command(name="listroles", description="List all roles in this server")
    async def listroles(self, interaction: discord.Interaction):
        roles = sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True)
        lines = [f"{r.mention} — {len(r.members)} member(s)" for r in roles if r.name != "@everyone"]
        embed = discord.Embed(title=f"Roles in {interaction.guild.name}", description="\n".join(lines[:25]) or "No roles.", color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="View bot statistics")
    async def botinfo(self, interaction: discord.Interaction):
        uptime_seconds = int(time.time() - START_TIME)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        embed = discord.Embed(title="🤖 Bot Info", color=discord.Color.blurple())
        embed.add_field(name="Servers", value=len(self.bot.guilds))
        embed.add_field(name="Users", value=sum(g.member_count for g in self.bot.guilds))
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms")
        embed.add_field(name="Uptime", value=f"{hours}h {minutes}m {seconds}s")
        embed.add_field(name="discord.py", value=discord.__version__)
        embed.add_field(name="Python", value=platform.python_version())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sync", description="Re-sync slash commands with Discord (Bot owner only)")
    @is_bot_owner()
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        synced = await self.bot.tree.sync()
        await interaction.followup.send(embed=success_embed(f"Synced {len(synced)} command(s)."), ephemeral=True)

    @app_commands.command(name="reload", description="Reload a cog without restarting the bot (Bot owner only)")
    @app_commands.describe(cog="Cog module name, e.g. moderation")
    @is_bot_owner()
    async def reload(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await interaction.response.send_message(embed=success_embed(f"Reloaded `{cog}`"), ephemeral=True)
        except commands.ExtensionError as e:
            await interaction.response.send_message(embed=error_embed(f"Failed to reload `{cog}`: {e}"), ephemeral=True)

    @app_commands.command(name="shutdown", description="Shut the bot down (Bot owner only)")
    @is_bot_owner()
    async def shutdown(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=success_embed("Shutting down..."), ephemeral=True)
        await self.bot.close()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(embed=error_embed("You don't have permission to use this command."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error_embed(f"Something went wrong: {error}"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
