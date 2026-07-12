"""Reusable permission checks + a consistent error embed builder."""
import discord
from discord import app_commands


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {message}", color=discord.Color.red())


def success_embed(message: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {message}", color=discord.Color.green())


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        raise app_commands.MissingPermissions(["administrator"])
    return app_commands.check(predicate)


def is_mod():
    """Passes for admins, or anyone with kick/ban/manage_messages (typical 'staff' perms)."""
    async def predicate(interaction: discord.Interaction) -> bool:
        perms = interaction.user.guild_permissions
        if perms.administrator or perms.kick_members or perms.ban_members or perms.manage_messages:
            return True
        raise app_commands.MissingPermissions(["kick_members", "ban_members", "manage_messages"])
    return app_commands.check(predicate)


def is_bot_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        app_info = await interaction.client.application_info()
        if interaction.user.id == app_info.owner.id:
            return True
        raise app_commands.MissingPermissions(["bot_owner"])
    return app_commands.check(predicate)
