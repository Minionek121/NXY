import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
import random

from utils.checks import is_admin, error_embed


class GiveawayView(discord.ui.View):
    def __init__(self, cog: "Giveaways", giveaway_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.success, custom_id="giveaway_enter_btn")
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = self.cog.active.get(self.giveaway_id)
        if not giveaway:
            return await interaction.response.send_message("❌ This giveaway has ended.", ephemeral=True)
        if interaction.user.id in giveaway["participants"]:
            return await interaction.response.send_message("✅ You already entered this giveaway!", ephemeral=True)
        giveaway["participants"].append(interaction.user.id)
        await interaction.response.send_message("🎉 You entered the giveaway! Good luck!", ephemeral=True)


class Giveaways(commands.Cog):
    """Timed giveaways with a button-based entry system. State is in-memory (giveaways don't survive a restart)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active: dict[int, dict] = {}

    async def _end_giveaway(self, giveaway_id: int, channel: discord.TextChannel):
        giveaway = self.active.get(giveaway_id)
        if not giveaway:
            return
        participants = giveaway["participants"]

        if not participants:
            embed = discord.Embed(title="🎉 Giveaway Ended - No Winner", description=f"**Prize:** {giveaway['prize']}\n\n❌ No one entered.", color=discord.Color.red())
        else:
            pool = participants.copy()
            winners = []
            for _ in range(min(giveaway["winners"], len(pool))):
                winner_id = random.choice(pool)
                pool.remove(winner_id)
                winners.append(winner_id)
            mentions = "\n".join(f"🏆 <@{wid}>" for wid in winners)
            embed = discord.Embed(title="🎉 Giveaway Ended!", description=f"**Prize:** {giveaway['prize']}\n\n{mentions}\n**Total Entries:** {len(participants)}", color=discord.Color.gold())

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

        self.active.pop(giveaway_id, None)

    @app_commands.command(name="giveaway_start", description="Start a giveaway (Admin only)")
    @app_commands.describe(prize="What are you giving away?", duration="Duration in minutes (1-1440)", winners="Number of winners")
    @is_admin()
    async def giveaway_start(self, interaction: discord.Interaction, prize: str, duration: app_commands.Range[int, 1, 1440], winners: app_commands.Range[int, 1, None] = 1):
        giveaway_id = int(datetime.now().timestamp())
        end_time = datetime.now() + timedelta(minutes=duration)
        self.active[giveaway_id] = {"prize": prize, "participants": [], "winners": winners, "end_time": end_time}

        embed = discord.Embed(
            title="🎉 GIVEAWAY!",
            description=f"**Prize:** {prize}\n\n**Ends:** <t:{int(end_time.timestamp())}:R>\n**Winners:** {winners}",
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Giveaway ID: {giveaway_id}")

        await interaction.response.send_message(embed=embed, view=GiveawayView(self, giveaway_id))

        async def _wait():
            await asyncio.sleep(duration * 60)
            await self._end_giveaway(giveaway_id, interaction.channel)

        self.bot.loop.create_task(_wait())

    @app_commands.command(name="giveaway_end", description="End a giveaway immediately (Admin only)")
    @app_commands.describe(giveaway_id="The giveaway ID to end")
    @is_admin()
    async def giveaway_end(self, interaction: discord.Interaction, giveaway_id: str):
        try:
            gid = int(giveaway_id)
        except ValueError:
            return await interaction.response.send_message(embed=error_embed("Invalid giveaway ID."), ephemeral=True)
        if gid not in self.active:
            return await interaction.response.send_message(embed=error_embed("Giveaway not found."), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self._end_giveaway(gid, interaction.channel)
        await interaction.followup.send("✅ Giveaway ended!", ephemeral=True)

    @app_commands.command(name="giveaway_list", description="List all active giveaways")
    async def giveaway_list(self, interaction: discord.Interaction):
        if not self.active:
            return await interaction.response.send_message(embed=discord.Embed(title="🎉 Active Giveaways", description="No active giveaways.", color=discord.Color.blue()), ephemeral=True)

        description = ""
        for gid, gw in self.active.items():
            remaining = (gw["end_time"] - datetime.now()).total_seconds()
            if remaining > 0:
                description += f"**ID:** {gid}\n**Prize:** {gw['prize']}\n**Entries:** {len(gw['participants'])}\n**Time left:** {int(remaining // 60)}m\n\n"
        embed = discord.Embed(title="🎉 Active Giveaways", description=description or "No active giveaways.", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
