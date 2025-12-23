#once again had too much fun with comments
#fixed event_map with correct event ids that i wasnt able to catch out before smh, seems to be fine now atleast :) 

import discord
from discord.ext import commands
import aiohttp
import os
import time

API_KEY = os.getenv("RE_API_KEY")

SIGS_CHANNEL_ID = 1338692373042954260  # Roles channel id

EVENT_MAP = {
    "SHOW ME GATEWAY": {
        "event_ids": [60069],
        "role_id": 1440753757565620305
    },
    "BIXBY'S FROSTBYTE FRENZY": {
        "event_ids": [60081],
        "role_id": 1440753999379697747
    },
    "SCORE SHOWDOWN": {
        "event_ids": [59912, 55565, 59910],
        "role_id": 1440754038076608643
    },
    "FUN IN THE SUN": {
        "event_ids": [59968, 60127],
        "role_id": 1440754057940566027
    },
    "KALAHARI CLASSIC": {
        "event_ids": [60025, 60166],
        "role_id": 1440754084889231614
    },
}


# ─────────────────────────────
# UI COMPONENTS
# ─────────────────────────────

class TeamNumberModal(discord.ui.Modal, title="Submit Team Number"):
    def __init__(self, cog: "Sigs"):
        super().__init__()
        self.cog = cog

        self.team_number = discord.ui.TextInput(
            label="Team Number",
            placeholder="eg. 101A",
            max_length=32,
            required=True
        )
        self.add_item(self.team_number)

    async def on_submit(self, interaction: discord.Interaction):
        if self.cog.is_rate_limited():
            await interaction.response.send_message(
                embed=self.cog.make_high_traffic_embed(),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        team_number = self.team_number.value.strip().upper()
        await self.cog.process_team_number(interaction, team_number)


class TeamNumberView(discord.ui.View):
    def __init__(self, cog: "Sigs", author: discord.Member):
        super().__init__(timeout=None)
        self.cog = cog
        self.author = author

    @discord.ui.button(label="Submit Team Number", style=discord.ButtonStyle.primary)
    async def submit_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.cog.is_rate_limited():
            await interaction.response.send_message(
                embed=self.cog.make_high_traffic_embed(),
                ephemeral=True
            )
            return

        await interaction.response.send_modal(TeamNumberModal(self.cog))


class RemoveRolesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Remove all event roles", style=discord.ButtonStyle.danger)
    async def remove_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        event_role_ids = {info["role_id"] for info in EVENT_MAP.values()}
        roles_to_remove = [r for r in member.roles if r.id in event_role_ids]

        if not roles_to_remove:
            await interaction.response.send_message(
                "You do not currently have any event roles to remove.",
                ephemeral=True
            )
            return

        try:
            await member.remove_roles(*roles_to_remove)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I do not have permission to remove roles.",
                ephemeral=True
            )
            return

        removed_names = ", ".join(role.name for role in roles_to_remove)
        await interaction.response.send_message(
            f"✅ Removed roles: **{removed_names}**",
            ephemeral=True
        )


# ─────────────────────────────
# MAIN COG
# ─────────────────────────────

class Sigs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rate_limited_until = 0.0

    # ───── Rate limit helpers ─────

    def is_rate_limited(self) -> bool:
        return time.time() < self.rate_limited_until

    def set_rate_limit(self, seconds: int = 120):
        self.rate_limited_until = time.time() + seconds

    def make_high_traffic_embed(self) -> discord.Embed:
        return discord.Embed(
            title="High Traffic Right Now!",
            description="Please try again later.",
            color=discord.Color.red()
        )

    # ───── Core reusable panel sender ─────

    async def send_sigs_panel(self, channel: discord.TextChannel, author: discord.Member):
        embed = discord.Embed(
            title="Event Signature Check",
            description=(
                "**Please input your *team number* using the button below.**\n\n"
                "If your team is registered in any of these events, "
                "you will automatically receive the corresponding roles:\n\n"
                "• Show Me Gateway\n"
                "• Bixby's FrostByte Frenzy\n"
                "• SCORE Showdown\n"
                "• Fun in the Sun\n"
                "• Kalahari Classic\n"
                "• Worlds 2026 (Coming Soon!)\n\n"
                "_You have 60 seconds after clicking the button to submit._"
            ),
            color=discord.Color.blurple()
        )

        await channel.send(
            embed=embed,
            view=TeamNumberView(self, author)
        )

        remove_embed = discord.Embed(
            title="Remove Your Pre-Existing Roles",
            description=(
                "Use the button below to remove any event roles you no longer want.\n\n"
                "Clicking it will remove all tracked event roles from you if you have them."
            ),
            color=discord.Color.red()
        )

        await channel.send(embed=remove_embed, view=RemoveRolesView())

    # ───── Team processing logic ─────

    async def process_team_number(self, interaction: discord.Interaction, team_number: str):
        if self.is_rate_limited():
            await interaction.followup.send(
                embed=self.make_high_traffic_embed(),
                ephemeral=True
            )
            return

        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }

        member = interaction.user
        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        roles_to_add = []

        async with aiohttp.ClientSession() as session:
            for info in EVENT_MAP.values():
                for event_id in info["event_ids"]:
                    url = (
                        f"https://www.robotevents.com/api/v2/events/{event_id}/teams"
                        f"?number%5B%5D={team_number}&myTeams=false"
                    )

                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 429:
                            self.set_rate_limit()
                            await interaction.followup.send(
                                embed=self.make_high_traffic_embed(),
                                ephemeral=True
                            )
                            return

                        if resp.status != 200:
                            continue

                        data = await resp.json()
                        if not data.get("data"):
                            continue

                        role = guild.get_role(info["role_id"])
                        if role and role not in roles_to_add:
                            roles_to_add.append(role)
                        break

        all_event_role_ids = {info["role_id"] for info in EVENT_MAP.values()}
        roles_to_remove = [
            r for r in member.roles
            if r.id in all_event_role_ids and r not in roles_to_add
        ]

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove)
            if roles_to_add:
                await member.add_roles(*roles_to_add)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I do not have permission to add or remove roles.",
                ephemeral=True
            )
            return

        if not roles_to_add:
            await interaction.followup.send(
                "❌ You are **not registered** in any of the specified events. "
                "Any previous event roles have been removed.",
                ephemeral=True
            )
            return

        role_names = ", ".join(role.name for role in roles_to_add)
        await interaction.followup.send(
            f"✅ Roles added: **{role_names}**. Any previous event roles have been removed.",
            ephemeral=True
        )

    # ───── User-facing command ─────

    @commands.command(name="sigs")
    async def sigs(self, ctx):
        if ctx.channel.id != SIGS_CHANNEL_ID:
            await ctx.send("This command is not allowed to be sent here.")
            return

        await self.send_sigs_panel(ctx.channel, ctx.author)


async def setup(bot):
    await bot.add_cog(Sigs(bot))
