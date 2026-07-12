import discord
from discord import app_commands
from discord.ext import commands
import random
import hashlib

EIGHTBALL_RESPONSES = [
    "It is certain.", "Without a doubt.", "Yes, definitely.", "You may rely on it.",
    "As I see it, yes.", "Most likely.", "Outlook good.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Concentrate and ask again.", "Don't count on it.",
    "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful.",
]

JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I told my computer I needed a break, and it said 'no problem, I'll go to sleep too.'",
    "Why did the developer go broke? Because they used up all their cache.",
    "There are 10 types of people: those who understand binary and those who don't.",
    "A SQL query walks into a bar, walks up to two tables and asks: 'Can I join you?'",
    "Why do Java developers wear glasses? Because they don't C#.",
    "I would tell you a UDP joke, but you might not get it.",
]

FACTS = [
    "Octopuses have three hearts and blue blood.",
    "Honey never spoils — archaeologists have found 3,000-year-old honey that's still edible.",
    "A day on Venus is longer than a year on Venus.",
    "Bananas are botanically berries, but strawberries aren't.",
    "The Eiffel Tower can grow taller in summer due to thermal expansion.",
    "Wombat droppings are cube-shaped.",
]

HUG_GIFS = ["🤗"]  # placeholder emoji reactions; swap for real GIF URLs if you add a Tenor API key


class Fun(commands.Cog):
    """Games and light entertainment commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question")
    @app_commands.describe(question="Your question")
    async def eightball(self, interaction: discord.Interaction, question: str):
        # Deterministic-ish per question so repeated asks aren't purely random spam, but varies by asker/time via random
        answer = random.choice(EIGHTBALL_RESPONSES)
        embed = discord.Embed(title="🎱 Magic 8-Ball", color=discord.Color.dark_purple())
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=answer, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Flip a coin")
    async def coinflip(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🪙 The coin landed on **{random.choice(['Heads', 'Tails'])}**!")

    @app_commands.command(name="dice", description="Roll one or more dice")
    @app_commands.describe(sides="Number of sides per die", count="Number of dice to roll")
    async def dice(self, interaction: discord.Interaction, sides: app_commands.Range[int, 2, 1000] = 6, count: app_commands.Range[int, 1, 20] = 1):
        rolls = [random.randint(1, sides) for _ in range(count)]
        await interaction.response.send_message(f"🎲 Rolled {count}d{sides}: **{', '.join(map(str, rolls))}** (total: {sum(rolls)})")

    @app_commands.command(name="rps", description="Play rock-paper-scissors against the bot")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Rock", value="rock"),
        app_commands.Choice(name="Paper", value="paper"),
        app_commands.Choice(name="Scissors", value="scissors"),
    ])
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
        bot_choice = random.choice(["rock", "paper", "scissors"])
        user_choice = choice.value
        if user_choice == bot_choice:
            result = "It's a tie!"
        elif (user_choice, bot_choice) in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]:
            result = "You win! 🎉"
        else:
            result = "I win! 🤖"
        await interaction.response.send_message(f"You picked **{user_choice}**, I picked **{bot_choice}**. {result}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
