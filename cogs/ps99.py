"""
Pet Simulator 99 stats — backed by Big Games' official public API
(docs: github.com/BIG-Games-LLC/ps99-public-api-docs, no API key required).

Important caveat baked into the API itself: /v1/clans/players is an
*aggregate sampled from the top 25 clans by all-time battle points*, not a
full clan directory. If a clan/player doesn't show up here, it usually means
their clan isn't in that top-25 sample — not that they don't exist in-game.
"""
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp

from utils.checks import error_embed
import config


class PS99(commands.Cog, name="PS99"):
    """Pet Simulator 99 clan and player stats."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get(self, path: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.PS99_API_BASE}{path}") as resp:
                data = await resp.json()
                return resp.status, data

    @app_commands.command(name="ps99_clan", description="Look up a Pet Simulator 99 clan's stats (top-25 sample)")
    @app_commands.describe(clan_name="Exact clan name (case-insensitive)")
    async def ps99_clan(self, interaction: discord.Interaction, clan_name: str):
        await interaction.response.defer()
        status, payload = await self._get("/v1/clans/players")

        if status != 200 or payload.get("status") != "ok":
            return await interaction.followup.send(embed=error_embed("Couldn't reach the PS99 API right now. Try again shortly."))

        players = payload["data"]["players"]
        matches = [p for p in players if p.get("Clan", {}).get("Name", "").lower() == clan_name.lower()]

        if not matches:
            return await interaction.followup.send(embed=error_embed(
                f"No clan named **{clan_name}** found in the current top-{payload['data']['sampledClans']} sample. "
                "Small/inactive clans often aren't in this window."
            ))

        clan_info = matches[0]["Clan"]
        total_diamonds = sum(p.get("AllTimeDiamonds", 0) for p in matches)
        total_active_points = sum(p.get("ActiveBattlePoints", 0) for p in matches)
        top_players = sorted(matches, key=lambda p: p.get("AllTimeDiamonds", 0), reverse=True)[:5]

        embed = discord.Embed(title=f"🏰 Clan: {clan_info['Name']}", color=discord.Color.blue())
        if clan_info.get("Icon"):
            embed.set_thumbnail(url=f"https://www.roblox.com/asset-thumbnail/image?assetId={clan_info['Icon'].replace('rbxassetid://', '')}&width=150&height=150&format=png")
        embed.add_field(name="Country", value=clan_info.get("CountryCode", "—"))
        embed.add_field(name="Sampled Members", value=len(matches))
        if "Place" in clan_info:
            embed.add_field(name="Current Battle Place", value=clan_info["Place"])
        embed.add_field(name="Total All-Time Diamonds (sampled members)", value=f"{total_diamonds:,}", inline=False)
        embed.add_field(name="Total Active Battle Points (sampled members)", value=f"{total_active_points:,}", inline=False)

        top_list = "\n".join(f"**{p['DisplayName']}** — {p.get('AllTimeDiamonds', 0):,} 💎" for p in top_players)
        embed.add_field(name="Top members by diamonds", value=top_list or "—", inline=False)
        embed.set_footer(text=f"Data drawn from top {payload['data']['sampledClans']} clans by battle points — biggamesapi.io")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="ps99_player", description="Look up a Pet Simulator 99 player by Roblox user ID")
    @app_commands.describe(user_id="The player's numeric Roblox user ID")
    async def ps99_player(self, interaction: discord.Interaction, user_id: str):
        if not user_id.isdigit():
            return await interaction.response.send_message(embed=error_embed("That doesn't look like a numeric Roblox user ID."), ephemeral=True)

        await interaction.response.defer()
        status, payload = await self._get(f"/v1/clans/players/{user_id}")

        if status == 404:
            return await interaction.followup.send(embed=error_embed("That player isn't in the current top-clan sample (their clan may not be top-25 by battle points)."))
        if status != 200 or payload.get("status") != "ok":
            return await interaction.followup.send(embed=error_embed("Couldn't reach the PS99 API right now. Try again shortly."))

        p = payload["data"]["player"]
        clan = p.get("Clan", {})
        embed = discord.Embed(title=f"👤 {p['DisplayName']}", color=discord.Color.green())
        embed.add_field(name="Clan", value=clan.get("Name", "—"))
        embed.add_field(name="All-Time Diamonds", value=f"{p.get('AllTimeDiamonds', 0):,}")
        embed.add_field(name="Active Battle Points", value=f"{p.get('ActiveBattlePoints', 0):,}")
        embed.add_field(name="Total Battles", value=p.get("TotalBattles", 0))
        embed.add_field(name="Earned Medals", value=p.get("EarnedMedals", 0))
        embed.add_field(name="Avg. Placement", value=p.get("AvgPlace") if p.get("AvgPlace") is not None else "—")
        embed.set_footer(text="biggamesapi.io — top-clan sample")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="ps99_battle", description="Look up a Pet Simulator 99 clan battle by its ID")
    @app_commands.describe(battle_id="The battle's configName, e.g. GuildBattle_Spring2025")
    async def ps99_battle(self, interaction: discord.Interaction, battle_id: str):
        await interaction.response.defer()
        status, payload = await self._get(f"/v1/clans/battles/{battle_id}")

        if status == 404:
            return await interaction.followup.send(embed=error_embed("No battle found with that ID."))
        if status != 200 or payload.get("status") != "ok":
            return await interaction.followup.send(embed=error_embed("Couldn't reach the PS99 API right now. Try again shortly."))

        data = payload["data"]
        meta, stats = data["meta"], data["stats"]

        embed = discord.Embed(title=f"⚔️ {meta['title']}", description=f"State: **{meta['state']}**", color=discord.Color.dark_gold())
        embed.add_field(name="Participating Clans", value=stats["participatingClans"])
        embed.add_field(name="Total Clan Points", value=f"{stats['totalClanPoints']:,}")
        embed.add_field(name="Contributors", value=stats["totalContributors"])

        top_clans = "\n".join(f"**#{c['rank']} {c['name']}** — {c['points']:,} pts" for c in data.get("topClans", [])[:5])
        embed.add_field(name="Top Clans", value=top_clans or "—", inline=False)

        top_players = "\n".join(f"**#{p['rank']} {p['displayName']}** — {p['points']:,} pts" for p in data.get("topPlayers", [])[:5])
        embed.add_field(name="Top Players", value=top_players or "—", inline=False)

        embed.set_footer(text="biggamesapi.io")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PS99(bot))
