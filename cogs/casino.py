"""
Casino cog — a virtual, in-server currency economy. No real money is
involved anywhere in this cog; balances are just numbers in a JSON file
scoped per-guild, used for fun leaderboard/gambling-style minigames.
"""
import discord
from discord import app_commands
from discord.ext import commands
import random
import time

from utils.database import JSONStore
from utils.checks import error_embed, success_embed
import config

economy_db = JSONStore("economy")  # {guild_id: {user_id: {"balance": int, "last_daily": ts, "last_work": ts}}}


def _account(guild_id: int, user_id: int) -> dict:
    data = economy_db.get(guild_id, {})
    acc = data.get(str(user_id))
    if acc is None:
        acc = {"balance": config.STARTING_BALANCE, "last_daily": 0, "last_work": 0}
        data[str(user_id)] = acc
        economy_db.set(guild_id, data)
    return acc


def _save(guild_id: int, user_id: int, acc: dict):
    data = economy_db.get(guild_id, {})
    data[str(user_id)] = acc
    economy_db.set(guild_id, data)


def _fmt_cooldown(seconds_left: int) -> str:
    h, rem = divmod(seconds_left, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if not h and not m:
        parts.append(f"{s}s")
    return " ".join(parts)


class Casino(commands.Cog):
    """Virtual-currency economy games (coins, slots, blackjack, roulette)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your (or someone else's) coin balance")
    @app_commands.describe(member="Member to check (defaults to you)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        acc = _account(interaction.guild.id, member.id)
        await interaction.response.send_message(f"💰 **{member.display_name}** has **{acc['balance']:,}** coins.")

    @app_commands.command(name="daily", description="Claim your daily coin reward")
    async def daily(self, interaction: discord.Interaction):
        acc = _account(interaction.guild.id, interaction.user.id)
        now = time.time()
        elapsed = now - acc["last_daily"]
        if elapsed < config.DAILY_COOLDOWN_SECONDS:
            remaining = int(config.DAILY_COOLDOWN_SECONDS - elapsed)
            return await interaction.response.send_message(embed=error_embed(f"You already claimed today. Try again in {_fmt_cooldown(remaining)}."), ephemeral=True)
        acc["balance"] += config.DAILY_REWARD
        acc["last_daily"] = now
        _save(interaction.guild.id, interaction.user.id, acc)
        await interaction.response.send_message(embed=success_embed(f"You claimed your daily **{config.DAILY_REWARD:,}** coins! New balance: {acc['balance']:,}"))

    @app_commands.command(name="work", description="Work a shift for a random amount of coins")
    async def work(self, interaction: discord.Interaction):
        acc = _account(interaction.guild.id, interaction.user.id)
        now = time.time()
        elapsed = now - acc["last_work"]
        if elapsed < config.WORK_COOLDOWN_SECONDS:
            remaining = int(config.WORK_COOLDOWN_SECONDS - elapsed)
            return await interaction.response.send_message(embed=error_embed(f"You're on cooldown. Try again in {_fmt_cooldown(remaining)}."), ephemeral=True)
        earned = random.randint(config.WORK_MIN, config.WORK_MAX)
        acc["balance"] += earned
        acc["last_work"] = now
        _save(interaction.guild.id, interaction.user.id, acc)
        jobs = ["delivered packages", "walked dogs", "fixed bugs", "streamed on Twitch", "flipped burgers", "mowed lawns"]
        await interaction.response.send_message(embed=success_embed(f"You {random.choice(jobs)} and earned **{earned:,}** coins! New balance: {acc['balance']:,}"))

    @app_commands.command(name="beg", description="Beg for a small amount of coins (no cooldown, low reward)")
    async def beg(self, interaction: discord.Interaction):
        acc = _account(interaction.guild.id, interaction.user.id)
        amount = random.randint(0, 40)
        acc["balance"] += amount
        _save(interaction.guild.id, interaction.user.id, acc)
        if amount == 0:
            await interaction.response.send_message("😅 Nobody gave you anything this time.")
        else:
            await interaction.response.send_message(f"🙏 A stranger gave you **{amount}** coins.")

    @app_commands.command(name="give", description="Give coins to another member")
    @app_commands.describe(member="Who to give coins to", amount="Amount of coins")
    async def give(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, None]):
        if member.id == interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("You can't send coins to yourself."), ephemeral=True)
        sender = _account(interaction.guild.id, interaction.user.id)
        if sender["balance"] < amount:
            return await interaction.response.send_message(embed=error_embed("You don't have enough coins."), ephemeral=True)
        receiver = _account(interaction.guild.id, member.id)
        sender["balance"] -= amount
        receiver["balance"] += amount
        _save(interaction.guild.id, interaction.user.id, sender)
        _save(interaction.guild.id, member.id, receiver)
        await interaction.response.send_message(embed=success_embed(f"Sent **{amount:,}** coins to **{member.display_name}**"))

    @app_commands.command(name="leaderboard", description="View the richest members in this server")
    async def leaderboard(self, interaction: discord.Interaction):
        data = economy_db.get(interaction.guild.id, {})
        ranked = sorted(data.items(), key=lambda kv: kv[1]["balance"], reverse=True)[:10]
        if not ranked:
            return await interaction.response.send_message("No one has any coins yet.", ephemeral=True)
        lines = []
        for i, (uid, acc) in enumerate(ranked, 1):
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"Unknown ({uid})"
            lines.append(f"**{i}.** {name} — {acc['balance']:,} coins")
        embed = discord.Embed(title="🏆 Coin Leaderboard", description="\n".join(lines), color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rob", description="Attempt to rob coins from another member (risky!)")
    @app_commands.describe(member="Member to rob")
    async def rob(self, interaction: discord.Interaction, member: discord.Member):
        if member.id == interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("You can't rob yourself."), ephemeral=True)
        robber = _account(interaction.guild.id, interaction.user.id)
        victim = _account(interaction.guild.id, member.id)
        if victim["balance"] < 50:
            return await interaction.response.send_message(embed=error_embed(f"**{member.display_name}** doesn't have enough coins to be worth robbing."), ephemeral=True)

        if random.random() < 0.4:  # 40% success chance
            amount = random.randint(1, min(victim["balance"], 300))
            victim["balance"] -= amount
            robber["balance"] += amount
            outcome = f"🕵️ Success! You stole **{amount:,}** coins from **{member.display_name}**."
        else:
            fine = min(robber["balance"], random.randint(20, 150))
            robber["balance"] -= fine
            outcome = f"🚨 You got caught and paid a **{fine:,}** coin fine!"

        _save(interaction.guild.id, interaction.user.id, robber)
        _save(interaction.guild.id, member.id, victim)
        await interaction.response.send_message(outcome)

    # ---------- Games ----------

    @app_commands.command(name="slots", description="Bet coins on a slot machine spin")
    @app_commands.describe(bet="Amount of coins to bet")
    async def slots(self, interaction: discord.Interaction, bet: app_commands.Range[int, 1, None]):
        acc = _account(interaction.guild.id, interaction.user.id)
        if acc["balance"] < bet:
            return await interaction.response.send_message(embed=error_embed("You don't have enough coins for that bet."), ephemeral=True)

        symbols = ["🍒", "🍋", "🍇", "🔔", "⭐", "💎"]
        reels = [random.choice(symbols) for _ in range(3)]

        if reels[0] == reels[1] == reels[2]:
            multiplier = 10 if reels[0] == "💎" else 5
            winnings = bet * multiplier
            acc["balance"] += winnings
            outcome = f"JACKPOT! You won **{winnings:,}** coins!"
        elif len(set(reels)) == 2:
            winnings = bet
            acc["balance"] += winnings
            outcome = f"Small win! You won **{winnings:,}** coins!"
        else:
            acc["balance"] -= bet
            outcome = f"No match. You lost **{bet:,}** coins."

        _save(interaction.guild.id, interaction.user.id, acc)
        embed = discord.Embed(title="🎰 Slots", description=f"[ {' | '.join(reels)} ]\n\n{outcome}\n\nBalance: {acc['balance']:,}", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip_bet", description="Bet coins on a coin flip")
    @app_commands.describe(bet="Amount of coins to bet", choice="Heads or tails")
    @app_commands.choices(choice=[app_commands.Choice(name="Heads", value="heads"), app_commands.Choice(name="Tails", value="tails")])
    async def coinflip_bet(self, interaction: discord.Interaction, bet: app_commands.Range[int, 1, None], choice: app_commands.Choice[str]):
        acc = _account(interaction.guild.id, interaction.user.id)
        if acc["balance"] < bet:
            return await interaction.response.send_message(embed=error_embed("You don't have enough coins for that bet."), ephemeral=True)
        result = random.choice(["heads", "tails"])
        if result == choice.value:
            acc["balance"] += bet
            outcome = f"It landed on **{result}** — you won **{bet:,}** coins!"
        else:
            acc["balance"] -= bet
            outcome = f"It landed on **{result}** — you lost **{bet:,}** coins."
        _save(interaction.guild.id, interaction.user.id, acc)
        await interaction.response.send_message(f"🪙 {outcome}\nBalance: {acc['balance']:,}")

    @app_commands.command(name="roulette", description="Bet coins on roulette (red/black/green or a number 0-36)")
    @app_commands.describe(bet="Amount of coins to bet", choice="'red', 'black', 'green', or a number 0-36")
    async def roulette(self, interaction: discord.Interaction, bet: app_commands.Range[int, 1, None], choice: str):
        acc = _account(interaction.guild.id, interaction.user.id)
        if acc["balance"] < bet:
            return await interaction.response.send_message(embed=error_embed("You don't have enough coins for that bet."), ephemeral=True)

        number = random.randint(0, 36)
        red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        color = "green" if number == 0 else ("red" if number in red_numbers else "black")

        choice_lower = choice.strip().lower()
        won = False
        payout_multiplier = 0

        if choice_lower.isdigit():
            if int(choice_lower) == number:
                won, payout_multiplier = True, 35
        elif choice_lower in ("red", "black", "green"):
            if choice_lower == color:
                won, payout_multiplier = True, (14 if color == "green" else 2)

        if won:
            winnings = bet * payout_multiplier
            acc["balance"] += winnings
            outcome = f"You won **{winnings:,}** coins!"
        else:
            acc["balance"] -= bet
            outcome = f"You lost **{bet:,}** coins."

        _save(interaction.guild.id, interaction.user.id, acc)
        embed = discord.Embed(title="🎡 Roulette", description=f"Ball landed on **{number} ({color})**\n\n{outcome}\n\nBalance: {acc['balance']:,}", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="blackjack", description="Play a simplified round of blackjack against the dealer")
    @app_commands.describe(bet="Amount of coins to bet")
    async def blackjack(self, interaction: discord.Interaction, bet: app_commands.Range[int, 1, None]):
        acc = _account(interaction.guild.id, interaction.user.id)
        if acc["balance"] < bet:
            return await interaction.response.send_message(embed=error_embed("You don't have enough coins for that bet."), ephemeral=True)

        def draw_hand():
            deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]
            return [random.choice(deck), random.choice(deck)]

        def hand_value(hand):
            total = sum(hand)
            aces = hand.count(11)
            while total > 21 and aces:
                total -= 10
                aces -= 1
            return total

        player = draw_hand()
        dealer = draw_hand()
        while hand_value(dealer) < 17:
            dealer.append(random.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]))

        p_val, d_val = hand_value(player), hand_value(dealer)

        if p_val > 21:
            acc["balance"] -= bet
            outcome = f"You bust with {p_val}. You lost **{bet:,}** coins."
        elif d_val > 21 or p_val > d_val:
            winnings = bet if p_val != 21 else int(bet * 1.5)
            acc["balance"] += winnings
            outcome = f"You win! ({p_val} vs dealer's {d_val}) — **+{winnings:,}** coins."
        elif p_val == d_val:
            outcome = f"Push ({p_val} vs {d_val}) — bet returned."
        else:
            acc["balance"] -= bet
            outcome = f"Dealer wins ({d_val} vs your {p_val}). You lost **{bet:,}** coins."

        _save(interaction.guild.id, interaction.user.id, acc)
        embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.gold())
        embed.add_field(name="Your hand", value=f"{player} = {p_val}", inline=False)
        embed.add_field(name="Dealer hand", value=f"{dealer} = {d_val}", inline=False)
        embed.add_field(name="Result", value=outcome, inline=False)
        embed.set_footer(text=f"Balance: {acc['balance']:,}")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Casino(bot))
