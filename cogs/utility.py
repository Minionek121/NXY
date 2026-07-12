import discord
from discord import app_commands
from discord.ext import commands
import time
import asyncio

from utils.checks import success_embed, error_embed


class Utility(commands.Cog):
    """Everyday utility and info commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong! `{round(self.bot.latency * 1000)}ms`")

    @app_commands.command(name="userinfo", description="View info about a member")
    @app_commands.describe(member="Member to look up (defaults to you)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = discord.Embed(title=f"{member}", color=discord.Color.blurple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="Nickname", value=member.nick or "None")
        embed.add_field(name="Bot?", value="Yes" if member.bot else "No")
        embed.add_field(name="Joined server", value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown")
        embed.add_field(name="Account created", value=discord.utils.format_dt(member.created_at, "R"))
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) if roles else "None", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="View info about this server")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=str(guild.owner))
        embed.add_field(name="Members", value=guild.member_count)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "R"))
        embed.add_field(name="Text channels", value=len(guild.text_channels))
        embed.add_field(name="Voice channels", value=len(guild.voice_channels))
        embed.add_field(name="Roles", value=len(guild.roles))
        embed.add_field(name="Boosts", value=guild.premium_subscription_count)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Get a member's avatar")
    @app_commands.describe(member="Member to look up (defaults to you)")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = discord.Embed(title=f"{member}'s avatar", color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="banner", description="Get a member's profile banner (if set)")
    @app_commands.describe(member="Member to look up (defaults to you)")
    async def banner(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        user = await self.bot.fetch_user(member.id)
        if not user.banner:
            return await interaction.response.send_message(embed=error_embed(f"{member} doesn't have a banner set."), ephemeral=True)
        embed = discord.Embed(title=f"{member}'s banner", color=discord.Color.blurple())
        embed.set_image(url=user.banner.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="View info about a role")
    @app_commands.describe(role="Role to look up")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(title=f"Role: {role.name}", color=role.color)
        embed.add_field(name="ID", value=role.id)
        embed.add_field(name="Members", value=len(role.members))
        embed.add_field(name="Position", value=role.position)
        embed.add_field(name="Mentionable", value=role.mentionable)
        embed.add_field(name="Hoisted", value=role.hoist)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="channelinfo", description="View info about a channel")
    @app_commands.describe(channel="Channel to look up (defaults to current)")
    async def channelinfo(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel = None):
        channel = channel or interaction.channel
        embed = discord.Embed(title=f"Channel: {channel.name}", color=discord.Color.blurple())
        embed.add_field(name="ID", value=channel.id)
        embed.add_field(name="Type", value=str(channel.type))
        embed.add_field(name="Created", value=discord.utils.format_dt(channel.created_at, "R"))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="poll", description="Create a quick yes/no poll")
    @app_commands.describe(question="The poll question")
    async def poll(self, interaction: discord.Interaction, question: str):
        embed = discord.Embed(title="📊 Poll", description=question, color=discord.Color.blurple())
        embed.set_footer(text=f"Started by {interaction.user}")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    @app_commands.command(name="remindme", description="Set a reminder (DM'd to you)")
    @app_commands.describe(minutes="Minutes from now", reminder="What to remind you about")
    async def remindme(self, interaction: discord.Interaction, minutes: app_commands.Range[int, 1, 10080], reminder: str):
        await interaction.response.send_message(embed=success_embed(f"I'll remind you about \"{reminder}\" in {minutes} minute(s)."), ephemeral=True)

        async def _wait_and_notify():
            await asyncio.sleep(minutes * 60)
            try:
                await interaction.user.send(f"⏰ Reminder: {reminder}")
            except discord.Forbidden:
                pass

        self.bot.loop.create_task(_wait_and_notify())

    @app_commands.command(name="calculate", description="Evaluate a basic arithmetic expression")
    @app_commands.describe(expression="e.g. 12 * (4 + 3)")
    async def calculate(self, interaction: discord.Interaction, expression: str):
        import ast
        import operator as op
        ops = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
               ast.Pow: op.pow, ast.USub: op.neg, ast.Mod: op.mod}

        def _eval(node):
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in ops:
                return ops[type(node.op)](_eval(node.left), _eval(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
                return ops[type(node.op)](_eval(node.operand))
            raise ValueError("Unsupported expression")

        try:
            result = _eval(ast.parse(expression, mode="eval").body)
            await interaction.response.send_message(f"🧮 `{expression}` = **{result}**")
        except Exception:
            await interaction.response.send_message(embed=error_embed("That's not a valid arithmetic expression."), ephemeral=True)

    @app_commands.command(name="timestamp", description="Convert minutes-from-now into a Discord timestamp")
    @app_commands.describe(minutes="Minutes from now")
    async def timestamp(self, interaction: discord.Interaction, minutes: int):
        target = int(time.time()) + minutes * 60
        await interaction.response.send_message(
            f"`<t:{target}:F>` → <t:{target}:F>\n`<t:{target}:R>` → <t:{target}:R>"
        )

    @app_commands.command(name="base64encode", description="Encode text as base64")
    @app_commands.describe(text="Text to encode")
    async def base64encode(self, interaction: discord.Interaction, text: str):
        import base64
        encoded = base64.b64encode(text.encode()).decode()
        await interaction.response.send_message(f"`{encoded}`")

    @app_commands.command(name="base64decode", description="Decode a base64 string")
    @app_commands.describe(text="Base64 text to decode")
    async def base64decode(self, interaction: discord.Interaction, text: str):
        import base64
        try:
            decoded = base64.b64decode(text.encode()).decode()
            await interaction.response.send_message(f"`{decoded}`")
        except Exception:
            await interaction.response.send_message(embed=error_embed("That's not valid base64."), ephemeral=True)

    @app_commands.command(name="randomnumber", description="Get a random number in a range")
    @app_commands.describe(minimum="Lowest value", maximum="Highest value")
    async def randomnumber(self, interaction: discord.Interaction, minimum: int, maximum: int):
        import random
        if minimum >= maximum:
            return await interaction.response.send_message(embed=error_embed("Minimum must be less than maximum."), ephemeral=True)
        await interaction.response.send_message(f"🔢 {random.randint(minimum, maximum)}")

    @app_commands.command(name="membercount", description="Show the server's member count breakdown")
    async def membercount(self, interaction: discord.Interaction):
        guild = interaction.guild
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        embed = discord.Embed(title=f"{guild.name} — Member Count", color=discord.Color.blurple())
        embed.add_field(name="Total", value=guild.member_count)
        embed.add_field(name="Humans", value=humans)
        embed.add_field(name="Bots", value=bots)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="invite", description="Get an invite link for this bot")
    async def invite(self, interaction: discord.Interaction):
        app_info = await self.bot.application_info()
        url = discord.utils.oauth_url(app_info.id, permissions=discord.Permissions(administrator=True))
        await interaction.response.send_message(f"Invite me here: {url}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
