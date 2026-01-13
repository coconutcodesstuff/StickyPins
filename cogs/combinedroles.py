import discord
from discord.ext import commands
import aiohttp
import os
import json
import time

API_KEY = os.getenv("RE_API_KEY")
#straight up copypasted everything from my ide
COMBINED_CHANNEL_ID = 1338692373042954260  # i had no better name for it...

# ─────────────────────────────
# REGION ROLE MAP
# ─────────────────────────────

REGION_ROLE_MAP = {
    "US_WEST": 1455060797708566528,
    "US_CENTRAL": 1455060875135418368,
    "US_EAST": 1455060935948505169,
    "CANADA": 1455061003979980964,
    "EUROPE": 1455061043683397753,
    "ASIA_SOUTH": 1455061107319378024,
    "ASIA_EAST": 1455061180472234026,
    "ASIA_WEST": 1455061236491485295,
    "OCEANIA": 1455061337712361627,
    "OTHER": 1455061278983716915,
}

ALL_REGION_ROLE_IDS = set(REGION_ROLE_MAP.values())

US_WEST = {
    "California", "Oregon", "Washington", "Nevada", "Arizona", "Utah", "Idaho",
    "Alaska", "Hawaii", "Colorado", "New Mexico",
    "Montana", "Wyoming"
}

US_CENTRAL = {
    "Texas", "Oklahoma", "Kansas", "Missouri", "Arkansas", "Iowa", "Nebraska",
    "South Dakota", "North Dakota", "Minnesota", "Louisiana", "Wisconsin",
    "Illinois", "Michigan", "Indiana", "Ohio",
    "Kentucky", "Tennessee", "Mississippi", "Alabama"
}

US_EAST = {
    "New York", "New Jersey", "Pennsylvania", "Virginia", "Maryland",
    "Massachusetts", "Florida", "Georgia", "North Carolina", "South Carolina",
    "Rhode Island", "Connecticut", "Delaware", "Maine", "New Hampshire",
    "Vermont", "West Virginia", "District of Columbia"
}

EUROPE = {
    "Albania", "Andorra", "Armenia", "Austria", "Belarus", "Belgium",
    "Bosnia and Herzegovina", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", 
    "Denmark", "Estonia", "Finland", "France", "Georgia", "Germany", "Greece", "Hungary",
    "Iceland", "Ireland", "Italy", "Kazakhstan", "Latvia", "Liechtenstein", "Lithuania",
    "Luxembourg", "Malta", "Moldova", "Monaco", "Montenegro", "Netherlands", "North Macedonia",
    "Norway", "Poland", "Portugal", "Romania", "San Marino", "Serbia", "Slovakia", "Slovenia",
    "Spain", "Sweden", "Switzerland", "Turkey", "Ukraine", "United Kingdom", "Vatican City"
}

ASIA_EAST = {"China", "Japan", "South Korea", "Taiwan", "Mongolia", "Hong Kong", "Macau", "North Korea"}

ASIA_SOUTH = {
    "India", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal", "Bhutan", "Maldives", "Afghanistan",
    "Brunei", "Cambodia", "Indonesia", "Laos", "Malaysia", "Myanmar", "Philippines", "Singapore",
    "Thailand", "Timor-Leste", "Vietnam"
}

ASIA_WEST = {"United Arab Emirates","Saudi Arabia","Qatar","Israel","Azerbaijan","Bahrain","Iran",
            "Iraq","Jordan","Kuwait","Lebanon","Oman","Palestine","Syria","Yemen"}

OCEANIA = {
    "Australia", "New Zealand", "Papua New Guinea", "Fiji", "Solomon Islands", "Vanuatu",
    "Micronesia", "Palau", "Marshall Islands", "Nauru", "Kiribati", "Samoa", "Tonga", "Tuvalu"
}

# ─────────────────────────────
# EVENT MAP
# ─────────────────────────────

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
        "event_ids": [60025, 60166, 60141],
        "role_id": 1440754084889231614
    },
    "CREATE US OPEN - VIQRC ES/MS": {
        "event_ids": [60529, 60530],
        "role_id": 1455472019276562647
    },
}

ALL_EVENT_ROLE_IDS = {info["role_id"] for info in EVENT_MAP.values()}

# ─────────────────────────────
# UI COMPONENTS
# ─────────────────────────────

class CombinedTeamModal(discord.ui.Modal, title="Submit Team Number"):
    team_number = discord.ui.TextInput(
        label="Team Number; These are Never stored or saved",
        placeholder="eg. 101A",
        required=True,
        max_length=32,
    )

    def __init__(self, cog: "CombinedRoles", mode: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.mode = mode  # "sigs", "region", or "both"

    async def on_submit(self, interaction: discord.Interaction):
        if self.cog.is_rate_limited():
            await interaction.response.send_message(
                embed=self.cog.make_high_traffic_embed(),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        team_number = self.team_number.value.strip().upper()
        
        if self.mode == "sigs":
            await self.cog.process_sigs_only(interaction, team_number)
        elif self.mode == "region":
            await self.cog.process_region_only(interaction, team_number)
        elif self.mode == "both":
            await self.cog.process_both(interaction, team_number)


class CombinedRolesView(discord.ui.View):
    def __init__(self, cog: "CombinedRoles"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Signature Roles", style=discord.ButtonStyle.secondary, row=0)
    async def sigs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.cog.is_rate_limited():
            await interaction.response.send_message(
                embed=self.cog.make_high_traffic_embed(),
                ephemeral=True
            )
            return
        await interaction.response.send_modal(CombinedTeamModal(self.cog, "sigs"))

    @discord.ui.button(label="Region Roles", style=discord.ButtonStyle.secondary, row=0)
    async def region_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.cog.is_rate_limited():
            await interaction.response.send_message(
                embed=self.cog.make_high_traffic_embed(),
                ephemeral=True
            )
            return
        await interaction.response.send_modal(CombinedTeamModal(self.cog, "region"))

    @discord.ui.button(label="Both", style=discord.ButtonStyle.success, row=1)
    async def both_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.cog.is_rate_limited():
            await interaction.response.send_message(
                embed=self.cog.make_high_traffic_embed(),
                ephemeral=True
            )
            return
        await interaction.response.send_modal(CombinedTeamModal(self.cog, "both"))

    @discord.ui.button(label="Remove All Roles", style=discord.ButtonStyle.danger, row=1)
    async def remove_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        all_tracked_role_ids = ALL_EVENT_ROLE_IDS | ALL_REGION_ROLE_IDS
        roles_to_remove = [r for r in member.roles if r.id in all_tracked_role_ids]

        if not roles_to_remove:
            await interaction.response.send_message(
                "You do not currently have any event or region roles to remove.",
                ephemeral=True
            )
            return

        try:
            await member.remove_roles(*roles_to_remove)
            removed_names = ", ".join(role.name for role in roles_to_remove)
            await interaction.response.send_message(
                f"✅ Removed all tracked roles: **{removed_names}**",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I do not have permission to remove roles.",
                ephemeral=True
            )


# ─────────────────────────────
# MAIN COG
# ─────────────────────────────

class CombinedRoles(commands.Cog):
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

    # ───── Region classifier ─────

    def classify_region(self, country: str, region: str) -> int:
        if country == "United States":
            if region in US_WEST:
                return REGION_ROLE_MAP["US_WEST"]
            if region in US_CENTRAL:
                return REGION_ROLE_MAP["US_CENTRAL"]
            if region in US_EAST:
                return REGION_ROLE_MAP["US_EAST"]

        if country == "Canada":
            return REGION_ROLE_MAP["CANADA"]

        if country in EUROPE:
            return REGION_ROLE_MAP["EUROPE"]

        if country in ASIA_EAST:
            return REGION_ROLE_MAP["ASIA_EAST"]

        if country in ASIA_SOUTH:
            return REGION_ROLE_MAP["ASIA_SOUTH"]

        if country in ASIA_WEST:
            return REGION_ROLE_MAP["ASIA_WEST"]
        
        if country in OCEANIA:
            return REGION_ROLE_MAP["OCEANIA"]

        return REGION_ROLE_MAP["OTHER"]

    # ───── Fetch team location data ─────

    async def fetch_team_location(self, team_number: str):
        """Returns (country, region) tuple or None if not found"""
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "accept": "application/json"
        }

        url = f"https://www.robotevents.com/api/v2/teams?number={team_number}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()

                print("\n===== REGION LOOKUP API RESPONSE =====")
                print(json.dumps(data, indent=2))
                print("====================================\n")

                if not data.get("data"):
                    return None

                teams = data["data"]
                chosen = None

                # Prefer registered VIQRC
                for t in teams:
                    if t.get("program", {}).get("code") == "VIQRC" and t.get("registered"):
                        chosen = t
                        break

                # Fallback to registered V5RC
                if not chosen:
                    for t in teams:
                        if t.get("program", {}).get("code") == "V5RC" and t.get("registered"):
                            chosen = t
                            break

                if not chosen:
                    return None

                location = chosen.get("location", {})
                country = location.get("country")
                region = location.get("region")

                print(f"[REGION DEBUG] Program: {chosen['program']['code']}")
                print(f"[REGION DEBUG] Country: {country}")
                print(f"[REGION DEBUG] Region: {region}")
                #now this kinda doesnt matter rn but im still  keeping it for diagnostics
                return (country, region)

    # ───── Fetch event signature roles ─────

    async def fetch_event_roles(self, team_number: str, guild: discord.Guild):
        """Returns list of event roles to add"""
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }

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
                            return None  # Signal rate limit

                        if resp.status != 200:
                            continue

                        data = await resp.json()
                        if not data.get("data"):
                            continue

                        role = guild.get_role(info["role_id"])
                        if role and role not in roles_to_add:
                            roles_to_add.append(role)
                        break

        return roles_to_add

    # ───── Process signature roles only ─────

    async def process_sigs_only(self, interaction: discord.Interaction, team_number: str):
        member = interaction.user
        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        roles_to_add = await self.fetch_event_roles(team_number, guild)

        if roles_to_add is None:  # Rate limited
            await interaction.followup.send(
                embed=self.make_high_traffic_embed(),
                ephemeral=True
            )
            return

        roles_to_remove = [
            r for r in member.roles
            if r.id in ALL_EVENT_ROLE_IDS and r not in roles_to_add
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
                "❌ You are **not registered** in any of the specified events. There still *may* be time to sign up?"
                "Any previous event roles have been removed.",
                ephemeral=True
            )
            return

        role_names = ", ".join(role.name for role in roles_to_add)
        await interaction.followup.send(
            f"✅ Signature roles added: **{role_names}**. Any previous event roles have been removed; Your welcome :)",
            ephemeral=True
        )

    # ───── Process region roles only ─────

    async def process_region_only(self, interaction: discord.Interaction, team_number: str):
        member = interaction.user
        guild = interaction.guild

        location_data = await self.fetch_team_location(team_number)

        if location_data is None:
            await interaction.followup.send(
                "❌ Team not found or no registered teams available.",
                ephemeral=True
            )
            return

        country, region = location_data
        role_id = self.classify_region(country, region)
        role = guild.get_role(role_id)

        if not role:
            await interaction.followup.send(
                "❌ Region role ID's missing on server. Someone didnt plan it out correctly...",
                ephemeral=True
            )
            return

        to_remove = [r for r in member.roles if r.id in ALL_REGION_ROLE_IDS and r.id != role_id]
        
        try:
            if to_remove:
                await member.remove_roles(*to_remove)
            if role not in member.roles:
                await member.add_roles(role)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I do not have permission to add or remove roles. Sad...",
                ephemeral=True
            )
            return

        await interaction.followup.send(
            f"✅ Assigned region role: **{role.name}**",
            ephemeral=True
        )

    # ───── Process both sigs and region ─────

    async def process_both(self, interaction: discord.Interaction, team_number: str):
        member = interaction.user
        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                "❌ This command can only be used in a server. What are you doing in DMs trying to run this command?",
                ephemeral=True
            )
            return

        # Fetch both
        location_data = await self.fetch_team_location(team_number)
        event_roles = await self.fetch_event_roles(team_number, guild)

        if event_roles is None:  # Rate limited
            await interaction.followup.send(
                embed=self.make_high_traffic_embed(),
                ephemeral=True
            )
            return

        # Process region
        region_role = None
        if location_data:
            country, region = location_data
            role_id = self.classify_region(country, region)
            region_role = guild.get_role(role_id)

        # Remove old roles
        event_roles_to_remove = [
            r for r in member.roles
            if r.id in ALL_EVENT_ROLE_IDS and r not in event_roles
        ]
        
        region_roles_to_remove = []
        if region_role:
            region_roles_to_remove = [
                r for r in member.roles 
                if r.id in ALL_REGION_ROLE_IDS and r.id != region_role.id
            ]

        all_roles_to_remove = event_roles_to_remove + region_roles_to_remove
        all_roles_to_add = event_roles.copy()
        if region_role and region_role not in member.roles:
            all_roles_to_add.append(region_role)

        try:
            if all_roles_to_remove:
                await member.remove_roles(*all_roles_to_remove)
            if all_roles_to_add:
                await member.add_roles(*all_roles_to_add)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I do not have permission to add or remove roles.",
                ephemeral=True
            )
            return

        # Build response message
        messages = []
        
        if event_roles:
            event_names = ", ".join(role.name for role in event_roles)
            messages.append(f"**Signature Roles:** {event_names}")
        else:
            messages.append("**Signature Roles:** None (not registered in any events)")

        if region_role:
            messages.append(f"**Region Role:** {region_role.name}")
        else:
            messages.append("**Region Role:** Not found")

        await interaction.followup.send(
            "✅ Roles updated!\n\n" + "\n".join(messages),
            ephemeral=True
        )

    # ───── User-facing command ─────

    @commands.command(name="roles")
    async def roles(self, ctx):
        if ctx.channel.id != COMBINED_CHANNEL_ID:
            await ctx.send("This command can only be used in the designated channel.")
            return

        embed = discord.Embed(
            title="🎯 Role Assignment System",
            description=(
                "🏆 **Special Event Roles** - Get roles for events you're registered in:\n"
                "**Events supported:** Signature Events, CREATE U.S. Open, & World Championship 2026(Coming soon!)\n"
                "🌍 **Region Roles** - Get your region's role based on your team location\n\n"
                "2️⃣ **Both** - Get both signature and region roles at once\n\n"
                "_The inputted team no. is never saved, and is only used once._"
            ),
            color=discord.Color.green()
        )

        await ctx.send(embed=embed, view=CombinedRolesView(self))


async def setup(bot):
    await bot.add_cog(CombinedRoles(bot))
