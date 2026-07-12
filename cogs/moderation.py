import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta

from utils.database import JSONStore
from utils.checks import is_mod, is_admin, error_embed, success_embed

warnings_db = JSONStore("warnings")  # {guild_id: {user_id: [ {mod, reason, timestamp}, ... ]}}


class Moderation(commands.Cog):
    """Server moderation: kicks, bans, timeouts, warnings, purge, channel locks."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Kick / Ban ----------

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Member to kick", reason="Reason for the kick")
    @is_mod()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message(embed=error_embed("You can't kick someone with an equal/higher role."), ephemeral=True)
        try:
            await member.send(embed=discord.Embed(description=f"You were kicked from **{interaction.guild.name}**\nReason: {reason}", color=discord.Color.red()))
        except discord.Forbidden:
            pass
        await member.kick(reason=f"{interaction.user}: {reason}")
        await interaction.response.send_message(embed=success_embed(f"Kicked **{member}** — {reason}"))

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Member to ban", reason="Reason for the ban", delete_days="Days of messages to delete (0-7)")
    @is_mod()
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_days: app_commands.Range[int, 0, 7] = 0):
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message(embed=error_embed("You can't ban someone with an equal/higher role."), ephemeral=True)
        try:
            await member.send(embed=discord.Embed(description=f"You were banned from **{interaction.guild.name}**\nReason: {reason}", color=discord.Color.red()))
        except discord.Forbidden:
            pass
        await member.ban(reason=f"{interaction.user}: {reason}", delete_message_days=delete_days)
        await interaction.response.send_message(embed=success_embed(f"Banned **{member}** — {reason}"))

    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.describe(user_id="The user ID to unban", reason="Reason for the unban")
    @is_mod()
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            user = discord.Object(id=int(user_id))
            await interaction.guild.unban(user, reason=reason)
            await interaction.response.send_message(embed=success_embed(f"Unbanned user `{user_id}`"))
        except ValueError:
            await interaction.response.send_message(embed=error_embed("That's not a valid user ID."), ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message(embed=error_embed("That user isn't banned."), ephemeral=True)

    @app_commands.command(name="softban", description="Ban then immediately unban to purge messages, without a permanent ban")
    @app_commands.describe(member="Member to softban", reason="Reason")
    @is_mod()
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.ban(reason=f"Softban by {interaction.user}: {reason}", delete_message_days=1)
        await interaction.guild.unban(member, reason="Softban cleanup")
        await interaction.response.send_message(embed=success_embed(f"Softbanned **{member}** (messages purged, not permanently banned)"))

    # ---------- Timeout (mute) ----------

    @app_commands.command(name="mute", description="Timeout a member for a duration")
    @app_commands.describe(member="Member to mute", minutes="Duration in minutes (max 40320 = 28 days)", reason="Reason")
    @is_mod()
    async def mute(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "No reason provided"):
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.timeout(until, reason=f"{interaction.user}: {reason}")
        await interaction.response.send_message(embed=success_embed(f"Muted **{member}** for {minutes} minute(s) — {reason}"))

    @app_commands.command(name="unmute", description="Remove a member's timeout")
    @app_commands.describe(member="Member to unmute")
    @is_mod()
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        await member.timeout(None, reason=f"Unmuted by {interaction.user}")
        await interaction.response.send_message(embed=success_embed(f"Unmuted **{member}**"))

    # ---------- Warnings ----------

    @app_commands.command(name="warn", description="Warn a member (logged, stored per-server)")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning")
    @is_mod()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        data = warnings_db.get(interaction.guild.id, {})
        entry = data.setdefault(str(member.id), [])
        entry.append({"mod": str(interaction.user), "reason": reason, "timestamp": datetime.utcnow().isoformat()})
        warnings_db.set(interaction.guild.id, data)
        await interaction.response.send_message(embed=success_embed(f"Warned **{member}** — {reason} (total warnings: {len(entry)})"))
        try:
            await member.send(embed=discord.Embed(description=f"You were warned in **{interaction.guild.name}**\nReason: {reason}", color=discord.Color.orange()))
        except discord.Forbidden:
            pass

    @app_commands.command(name="warnings", description="View a member's warnings")
    @app_commands.describe(member="Member to check")
    @is_mod()
    async def warnings_cmd(self, interaction: discord.Interaction, member: discord.Member):
        data = warnings_db.get(interaction.guild.id, {})
        entry = data.get(str(member.id), [])
        if not entry:
            return await interaction.response.send_message(embed=success_embed(f"**{member}** has no warnings."), ephemeral=True)
        embed = discord.Embed(title=f"Warnings for {member}", color=discord.Color.orange())
        for i, w in enumerate(entry, 1):
            embed.add_field(name=f"#{i} — {w['mod']}", value=f"{w['reason']}\n<t:{int(datetime.fromisoformat(w['timestamp']).timestamp())}:R>", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unwarn", description="Remove a single warning from a member by index")
    @app_commands.describe(member="Member to unwarn", index="Warning number to remove (see /warnings)")
    @is_mod()
    async def unwarn(self, interaction: discord.Interaction, member: discord.Member, index: app_commands.Range[int, 1, None]):
        data = warnings_db.get(interaction.guild.id, {})
        entry = data.get(str(member.id), [])
        if index > len(entry):
            return await interaction.response.send_message(embed=error_embed("That warning number doesn't exist."), ephemeral=True)
        removed = entry.pop(index - 1)
        data[str(member.id)] = entry
        warnings_db.set(interaction.guild.id, data)
        await interaction.response.send_message(embed=success_embed(f"Removed warning #{index} for **{member}** — {removed['reason']}"))

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member")
    @app_commands.describe(member="Member to clear warnings for")
    @is_mod()
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        data = warnings_db.get(interaction.guild.id, {})
        data.pop(str(member.id), None)
        warnings_db.set(interaction.guild.id, data)
        await interaction.response.send_message(embed=success_embed(f"Cleared warnings for **{member}**"))

    # ---------- Channel management ----------

    @app_commands.command(name="purge", description="Bulk-delete messages in this channel")
    @app_commands.describe(amount="Number of messages to delete (1-100)", member="Only delete messages from this member (optional)")
    @is_mod()
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100], member: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        check = (lambda m: m.author.id == member.id) if member else None
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(embed=success_embed(f"Deleted {len(deleted)} message(s)."), ephemeral=True)

    @app_commands.command(name="lock", description="Lock this channel (deny @everyone send messages)")
    @is_mod()
    async def lock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message(embed=success_embed("Channel locked 🔒"))

    @app_commands.command(name="unlock", description="Unlock this channel")
    @is_mod()
    async def unlock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message(embed=success_embed("Channel unlocked 🔓"))

    @app_commands.command(name="slowmode", description="Set slowmode delay for this channel")
    @app_commands.describe(seconds="Delay in seconds (0 to disable, max 21600)")
    @is_mod()
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        await interaction.channel.edit(slowmode_delay=seconds)
        msg = f"Slowmode set to {seconds}s" if seconds else "Slowmode disabled"
        await interaction.response.send_message(embed=success_embed(msg))

    @app_commands.command(name="nickname", description="Change a member's nickname")
    @app_commands.describe(member="Member to rename", nickname="New nickname (leave blank to reset)")
    @is_mod()
    async def nickname(self, interaction: discord.Interaction, member: discord.Member, nickname: str = None):
        await member.edit(nick=nickname)
        await interaction.response.send_message(embed=success_embed(f"Updated nickname for **{member}**"))

    @app_commands.command(name="banlist", description="View the server's ban list")
    @is_mod()
    async def banlist(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        bans = [entry async for entry in interaction.guild.bans(limit=25)]
        if not bans:
            return await interaction.followup.send(embed=success_embed("No banned users."), ephemeral=True)
        lines = [f"**{b.user}** — {b.reason or 'No reason given'}" for b in bans]
        embed = discord.Embed(title="Banned Users", description="\n".join(lines), color=discord.Color.red())
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(embed=error_embed("You don't have permission to use this command."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=error_embed(f"Something went wrong: {error}"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
