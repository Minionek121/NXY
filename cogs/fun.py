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

    @app_commands.command(name="joke", description="Get a random joke")
    async def joke(self, interaction: discord.Interaction):
        await interaction.response.send_message(random.choice(JOKES))

    @app_commands.command(name="fact", description="Get a random fun fact")
    async def fact(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"💡 {random.choice(FACTS)}")

    @app_commands.command(name="ship", description="Calculate compatibility between two members")
    @app_commands.describe(user1="First person", user2="Second person")
    async def ship(self, interaction: discord.Interaction, user1: discord.Member, user2: discord.Member):
        seed = "".join(sorted([str(user1.id), str(user2.id)]))
        pct = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % 101
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        name = user1.display_name[:len(user1.display_name)//2 + 1] + user2.display_name[len(user2.display_name)//2:]
        embed = discord.Embed(title="💘 Ship-o-meter", description=f"**{user1.display_name}** + **{user2.display_name}** = **{name}**\n\n{bar} {pct}%", color=discord.Color.magenta())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="hug", description="Hug another member")
    async def hug(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(f"🤗 {interaction.user.mention} hugs {member.mention}!")

    @app_commands.command(name="slap", description="Slap another member (playfully)")
    async def slap(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(f"👋 {interaction.user.mention} slaps {member.mention} with a large trout!")

    @app_commands.command(name="kiss", description="Give another member a kiss")
    async def kiss(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(f"😘 {interaction.user.mention} kisses {member.mention}!")

    @app_commands.command(name="compliment", description="Send a random compliment to a member")
    async def compliment(self, interaction: discord.Interaction, member: discord.Member):
        compliments = [
            "is one of the most thoughtful people around.",
            "has great taste and even better ideas.",
            "brightens up every conversation.",
            "is way more capable than they give themselves credit for.",
        ]
        await interaction.response.send_message(f"✨ {member.mention} {random.choice(compliments)}")

    @app_commands.command(name="reverse", description="Reverse a piece of text")
    @app_commands.describe(text="Text to reverse")
    async def reverse(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message(text[::-1])

    @app_commands.command(name="trivia", description="Get a random trivia question")
    async def trivia(self, interaction: discord.Interaction):
        questions = [
            ("What planet is known as the Red Planet?", "Mars"),
            ("What is the largest ocean on Earth?", "The Pacific Ocean"),
            ("How many strings does a standard guitar have?", "Six"),
            ("What is the chemical symbol for gold?", "Au"),
            ("Which country invented pizza?", "Italy"),
        ]
        q, a = random.choice(questions)
        embed = discord.Embed(title="🧠 Trivia", description=q, color=discord.Color.teal())
        await interaction.response.send_message(embed=embed)
        await interaction.followup.send(f"||{a}||")

    @app_commands.command(name="riddle", description="Get a random riddle")
    async def riddle(self, interaction: discord.Interaction):
        riddles = [
            ("The more you take, the more you leave behind. What am I?", "Footsteps"),
            ("What has keys but no locks, space but no room?", "A keyboard"),
            ("What has to be broken before you can use it?", "An egg"),
        ]
        q, a = random.choice(riddles)
        embed = discord.Embed(title="🧩 Riddle", description=q, color=discord.Color.dark_teal())
        await interaction.response.send_message(embed=embed)
        await interaction.followup.send(f"||{a}||")

    @app_commands.command(name="wouldyourather", description="Get a random would-you-rather question")
    async def wouldyourather(self, interaction: discord.Interaction):
        options = [
            "have the ability to fly or be invisible?",
            "always be 10 minutes late or 20 minutes early?",
            "live without music or without movies?",
            "explore space or the deep ocean?",
        ]
        await interaction.response.send_message(f"🤔 Would you rather **{random.choice(options)}**")

    @app_commands.command(name="choose", description="Let the bot choose between options for you")
    @app_commands.describe(options="Comma-separated list of options")
    async def choose(self, interaction: discord.Interaction, options: str):
        choices = [o.strip() for o in options.split(",") if o.strip()]
        if len(choices) < 2:
            return await interaction.response.send_message("Give me at least two options, separated by commas.", ephemeral=True)
        await interaction.response.send_message(f"🤔 I choose: **{random.choice(choices)}**")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
