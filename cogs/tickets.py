import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import asyncio

from utils.database import JSONStore
from utils.checks import is_admin, success_embed, error_embed

ticket_config_db = JSONStore("ticket_config")  # {guild_id: {category_id, support_role_id, counter}}


class TicketModal(discord.ui.Modal, title="Support Ticket"):
    subject = discord.ui.TextInput(label="Subject", placeholder="What is your issue about?", max_length=100, required=True)
    description = discord.ui.TextInput(label="Description", placeholder="Describe your issue in detail", style=discord.TextStyle.paragraph, max_length=1000, required=True)

    def __init__(self, cog: "Tickets"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            channel = await self.cog.create_ticket_channel(interaction.guild, interaction.user, self.subject.value, self.description.value)
            await interaction.followup.send(f"✅ Ticket created! {channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=error_embed(f"Couldn't create the ticket: {e}"), ephemeral=True)


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("❌ Only staff can close this ticket.", ephemeral=True)
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


class TicketOpenView(discord.ui.View):
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, custom_id="ticket_open_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal(self.cog))


class Tickets(commands.Cog):
    """Support ticket system: buttons + modal, one channel per ticket."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Persistent views need to be registered once; safe to add repeatedly since discord.py dedupes by custom_id.
        bot.add_view(TicketOpenView(self))
        bot.add_view(TicketCloseView())

    def _cfg(self, guild_id: int) -> dict:
        return ticket_config_db.get(guild_id, {"category_id": None, "support_role_id": None, "counter": 0})

    async def create_ticket_channel(self, guild: discord.Guild, user: discord.Member, subject: str, description: str) -> discord.TextChannel:
        cfg = self._cfg(guild.id)

        category = guild.get_channel(cfg["category_id"]) if cfg["category_id"] else None
        if category is None:
            category = await guild.create_category("Support Tickets")
            cfg["category_id"] = category.id

        cfg["counter"] += 1
        ticket_config_db.set(guild.id, cfg)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        if cfg["support_role_id"]:
            role = guild.get_role(cfg["support_role_id"])
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        channel = await guild.create_text_channel(f"ticket-{cfg['counter']}", category=category, overwrites=overwrites)

        embed = discord.Embed(
            title="✅ Ticket Created",
            description=f"**Subject:** {subject}\n\n**Description:** {description}",
            color=discord.Color.green(),
            timestamp=datetime.now(),
        )
        embed.add_field(name="Ticket ID", value=f"#{cfg['counter']}", inline=False)
        embed.set_footer(text=f"Opened by {user.name}")
        await channel.send(user.mention, embed=embed, view=TicketCloseView())
        return channel

    @app_commands.command(name="setup_tickets", description="Post the ticket-creation panel (Admin only)")
    @app_commands.describe(support_role="Role that can view/manage tickets (optional)")
    @is_admin()
    async def setup_tickets(self, interaction: discord.Interaction, support_role: discord.Role = None):
        cfg = self._cfg(interaction.guild.id)
        if support_role:
            cfg["support_role_id"] = support_role.id
            ticket_config_db.set(interaction.guild.id, cfg)

        embed = discord.Embed(title="🎫 Support Tickets", description="Click the button below to create a support ticket.", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=TicketOpenView(self))

    @app_commands.command(name="ticket_stats", description="View ticket statistics for this server")
    async def ticket_stats(self, interaction: discord.Interaction):
        cfg = self._cfg(interaction.guild.id)
        await interaction.response.send_message(embed=success_embed(f"Total tickets created: **{cfg['counter']}**"), ephemeral=True)

    @app_commands.command(name="add_to_ticket", description="Add a member to the current ticket channel (Staff only)")
    @app_commands.describe(member="Member to add")
    async def add_to_ticket(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(embed=error_embed("Only staff can do this."), ephemeral=True)
        await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)
        await interaction.response.send_message(embed=success_embed(f"Added {member.mention} to this ticket."))

    @app_commands.command(name="remove_from_ticket", description="Remove a member from the current ticket channel (Staff only)")
    @app_commands.describe(member="Member to remove")
    async def remove_from_ticket(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(embed=error_embed("Only staff can do this."), ephemeral=True)
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(embed=success_embed(f"Removed {member.mention} from this ticket."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
