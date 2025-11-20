import discord
from discord.ext import commands
from discord import app_commands
import json
from datetime import datetime, timezone


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Shows StickyPins bot statistics.")
    async def stats(self, interaction: discord.Interaction):
        """Slash command version of stats."""

        # --- Uptime ---
        now = datetime.now(timezone.utc)
        uptime_delta = now - getattr(self.bot, "start_time", now)
        uptime_str = str(uptime_delta).split(".")[0]

        # --- Total stickies ever made ---
        total_stickies = 0
        data_file = getattr(self.bot, "DATA_FILE", None)
        if data_file:
            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                total_stickies = len(data)
            except Exception:
                total_stickies = 0

        bot_user = self.bot.user

        embed = discord.Embed(
            title="StickyPins Stats",
            color=discord.Color.blue()
        )

        embed.set_thumbnail(url=bot_user.avatar.url if bot_user.avatar else None)

        embed.add_field(name="Bot Name", value=bot_user.name, inline=True)
        embed.add_field(name="Bot ID", value=bot_user.id, inline=True)

        embed.add_field(
            name="📌 Total Stickies In Its History",
            value=str(total_stickies),
            inline=False
        )

        embed.add_field(
            name="Bot Created",
            value=bot_user.created_at.strftime("%Y-%m-%d"),
            inline=True
        )

        # Time bot joined *this* server
        embed.add_field(
            name="Joined This Server",
            value=interaction.guild.me.joined_at.strftime("%Y-%m-%d"),
            inline=True
        )

        embed.add_field(
            name="⏳ Uptime",
            value=uptime_str,
            inline=False
        )

        embed.add_field(
            name="Developer",
            value="<@1202369414721450005>",
            inline=False
        )

        embed.set_footer(text="If there are any bugs, issues, or vulnerabilities that you believe are within the bot, please contact @guardian_coconut via a Direct Message! Please Refrain from sharing vulnerabilities to keep everyone safe!")

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))
