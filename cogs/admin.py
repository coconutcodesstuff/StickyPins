#too lazy so gpt helped me out :D 
#Still messed it up rlly bad so all that effort of giving prompts was in vain
#wasted only 5 hours on this and some other stuff smh

import discord
from discord.ext import commands
import os

OWNER_ID = 1202369414721450005
GUILD_ID = int(os.getenv("GUILD_ID"))
SIGS_CHANNEL_ID = 1338692373042954260


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sigsregen")
    async def sigsregen(self, ctx):
        # ❌ Must be run in DMs
        if ctx.guild is not None:
            await ctx.send("❌ Run this command in my DMs.")
            return

        # ❌ Owner-only
        if ctx.author.id != OWNER_ID:
            await ctx.send("❌ You are not authorized to use this command.")
            return

        # Fetch guild
        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            await ctx.send("❌ Guild not found.")
            return

        # Fetch channel
        channel = guild.get_channel(SIGS_CHANNEL_ID)
        if not channel:
            await ctx.send("❌ Sigs channel not found.")
            return

        # Permission check
        perms = channel.permissions_for(guild.me)
        if not (perms.view_channel and perms.send_messages and perms.manage_messages):
            await ctx.send("❌ Missing permissions in sigs channel.")
            return

        # Fetch member (YOU, but as a Member)
        member = guild.get_member(ctx.author.id)
        if not member:
            await ctx.send("❌ You are not a member of the server.")
            return

        # Delete last 2 bot messages in sigs channel
        deleted = 0
        async for msg in channel.history(limit=15):
            if deleted >= 2:
                break
            if msg.author == self.bot.user:
                await msg.delete()
                deleted += 1

        # Get Sigs cog
        sigs_cog = self.bot.get_cog("Sigs")
        if not sigs_cog:
            await ctx.send("❌ Sigs cog is not loaded.")
            return

        # Send panel
        await sigs_cog.send_sigs_panel(channel, member)

        # Confirm
        await ctx.send("✅ Sigs panel regenerated successfully.")


async def setup(bot):
    await bot.add_cog(Admin(bot))
