import discord
from discord.ext import commands
import json
import os

OWNER_ID = #Use the same one as the one in primarybot.py
ALLOWED_ROLE_ID = None  # Will be decided soon

# Hardcoded path to the canonical stickydata.json used on the host
STICKY_JSON_PATH = "/home/container/StickyPins/stickydata.json"


class StickyDeactivator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def has_permission(self, ctx):
        if ctx.author.id == OWNER_ID:
            return True
        if ALLOWED_ROLE_ID and any(r.id == ALLOWED_ROLE_ID for r in ctx.author.roles):
            return True
        return False

    @commands.command(name="deactivate")
    async def deactivate(self, ctx, *thread_ids):
        """Deactivate (delete) sticky entries by thread ID."""
        if not self.has_permission(ctx):
            emb = discord.Embed(
                title="⛔ Permission Denied",
                description="You are not allowed to use this command.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=emb)

        if not thread_ids:
            emb = discord.Embed(
                title="⚠ Missing Thread IDs",
                description="Usage: `-deactivate <thread_id> <thread_id> ...>`",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=emb)

        removed = []
        not_found = []

        for tid in thread_ids:
            tid_str = str(tid)

            # Cancel running task if exists on the bot instance
            task = getattr(self.bot, "tasks", {}).pop(tid_str, None)
            if task:
                try:
                    task.cancel()
                except:
                    pass

            # Load JSON from the canonical path and set active = False for this thread
            changed = False
            try:
                if os.path.exists(STICKY_JSON_PATH):
                    with open(STICKY_JSON_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    entry = data.get(tid_str)
                    if isinstance(entry, dict):
                        entry["active"] = False
                        data[tid_str] = entry
                        with open(STICKY_JSON_PATH, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        changed = True
            except Exception:
                changed = False

            # Update live in-memory data on the bot to match
            entry_mem = getattr(self.bot, "sticky_data", {}).get(tid_str)
            if isinstance(entry_mem, dict):
                entry_mem["active"] = False
                self.bot.sticky_data[tid_str] = entry_mem

            # Flag this thread as deactivated so refresh_cycle stops immediately
            if hasattr(self.bot, "deactivated_threads"):
                self.bot.deactivated_threads[tid_str] = False

            if changed:
                removed.append(tid_str)
            else:
                not_found.append(tid_str)

        # Response Embed
        emb = discord.Embed(
            title="📘 Sticky Deactivation",
            description="Processed the provided thread IDs.",
            color=discord.Color.blue()
        )

        if removed:
            emb.add_field(name="Deactivated", value="\n".join(removed), inline=False)
        if not_found:
            emb.add_field(name="Not Found", value="\n".join(not_found), inline=False)

        await ctx.send(embed=emb)


async def setup(bot):
    await bot.add_cog(StickyDeactivator(bot))

#i didnt make all the comments in this hehe
