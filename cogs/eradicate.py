import discord
from discord.ext import commands
import json
import os
import shutil
import asyncio

OWNER_ID = 1202369414721450005
ALLOWED_ROLE_ID = None  # will be changed once alex sends it


class StickyEradicator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def has_permission(self, ctx):
        if ctx.author.id == OWNER_ID:
            return True
        if ALLOWED_ROLE_ID and any(r.id == ALLOWED_ROLE_ID for r in ctx.author.roles):
            return True
        return False

    async def ask_confirmation_dm(self, user: discord.User, thread_ids):
        emb = discord.Embed(
            title="Confirm Sticky Eradication",
            description=(
                "**This action is PERMANENT.**\n\n"
                "The following thread IDs will be completely removed:\n"
                + "\n".join(f"- `{tid}`" for tid in thread_ids)
                + "\n\nReact with ✅ to confirm or ❌ to cancel."
            ),
            color=discord.Color.orange(),
        )

        try:
            msg = await user.send(embed=emb)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
        except Exception:
            return False

        def check(reaction, u):
            return (
                u.id == user.id
                and reaction.message.id == msg.id
                and str(reaction.emoji) in ("✅", "❌")
            )

        try:
            reaction, _ = await self.bot.wait_for(
                "reaction_add", check=check, timeout=60
            )
            return str(reaction.emoji) == "✅"
        except asyncio.TimeoutError:
            return False

    @commands.command(name="eradicate")
    async def eradicate(self, ctx, *thread_ids):
        if not self.has_permission(ctx):
            return await ctx.send(
                embed=discord.Embed(
                    title="LMAO! Permission Denied",
                    description="You are not allowed to use this command.",
                    color=discord.Color.red(),
                )
            )

        if not thread_ids:
            return await ctx.send(
                embed=discord.Embed(
                    title="Missing Thread IDs",
                    description="Usage: `-eradicate <thread_id> <thread_id> ...>`",
                    color=discord.Color.orange(),
                )
            )

        thread_ids = [str(t) for t in thread_ids]

        confirmed = await self.ask_confirmation_dm(ctx.author, thread_ids)
        if not confirmed:
            return await ctx.send(
                embed=discord.Embed(
                    description="Sticky eradication cancelled or request timed out.",
                    color=discord.Color.red(),
                )
            )

        DATA_FILE = "/home/container/StickyPins/stickydata.json"
        MEDIA_DIR = "/home/container/StickyPins/sticky_media"
        os.makedirs(MEDIA_DIR, exist_ok=True)


        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        removed = []
        not_found = []
        media_deleted = []

        for tid in thread_ids:
            if tid not in data and tid not in self.bot.sticky_data:
                not_found.append(tid)
                continue

            # cancel refresh task
            task = self.bot.tasks.pop(tid, None)
            if task:
                task.cancel()

            # delete live sticky message
            entry = data.get(tid) or self.bot.sticky_data.get(tid)
            if isinstance(entry, dict):
                msg_id = entry.get("sticky_message_id")
                if msg_id:
                    try:
                        thread = await self.bot.fetch_channel(int(tid))
                        msg = await thread.fetch_message(msg_id)
                        await msg.delete()
                    except Exception:
                        pass

            # PERMANENTLY blacklist this thread, ts lwk kinda  broken imo but here i am still doing it
            self.bot.deactivated_threads[tid] = True

            # remove from memory + disk
            data.pop(tid, None)
            self.bot.sticky_data.pop(tid, None)

            # delete media
            media_path = os.path.join(MEDIA_DIR, tid)
            if os.path.isdir(media_path):
                try:
                    shutil.rmtree(media_path)
                    media_deleted.append(tid)
                except Exception:
                    pass

            removed.append(tid)

        # save canonical JSON
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        emb = discord.Embed(
            title="Sticky Eradication Complete",
            color=discord.Color.dark_red(),
        )
        if removed:
            emb.add_field(name="Eradicated", value="\n".join(removed), inline=False)
        if media_deleted:
            emb.add_field(name="Media Deleted", value="\n".join(media_deleted), inline=False)
        if not_found:
            emb.add_field(name="Not Found", value="\n".join(not_found), inline=False)

        await ctx.send(embed=emb)


async def setup(bot):
    await bot.add_cog(StickyEradicator(bot))
