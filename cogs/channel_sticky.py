#ts jst for channels instead of threads

import discord
from discord.ext import commands
import os
import json
import time
import asyncio
from datetime import datetime, timezone

# minimal constants / mirrors from primarybot.py
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
COOLDOWN_SECONDS = 60.0

def iso_now():
    return datetime.now(timezone.utc).isoformat()

class ChannelSticky(commands.Cog):
    """
    Simple per-channel sticky cog.
    Commands:
    -stick [text]   -> create a sticky in THIS channel (can include attachments on the invoking message)
    -unstick        -> remove sticky from THIS channel
    Notes:
    - Stores data in channel_stickydata.json (same entry shape as stickydata.json)
    - 60s cooldown between stick/unstick actions per channel
    - Will not replace an existing active sticky (must unstick first)
    """

  """
  gpt so tuff at making these descriptions
  """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_file = os.path.join(base_dir, "channel_stickydata.json")
        # prefer bot-provided media dir if present, otherwise project sticky_media
        self.media_dir = getattr(bot, "STICKY_MEDIA_DIR", os.path.join(base_dir, "sticky_media"))
        os.makedirs(self.media_dir, exist_ok=True)

        self._lock = asyncio.Lock()
        self._action_lock = {}     # channel_id(str) -> asyncio.Lock
        self._last_action = {}     # channel_id(str) -> monotonic timestamp
        self.sticky_data = {}
        self._tasks = {}           # channel_id(str) -> asyncio.Task
        self._load_data()

        # Resume refresh tasks for active channel stickies
        for cid, entry in self.sticky_data.items():
            if entry.get("active", False):
                self._ensure_refresh_task(cid)

    # ---------------- data IO ----------------
    def _load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                raw = {}
        else:
            raw = {}
        cleaned = {}
        for k, v in raw.items():
            try:
                ck = str(int(k))
            except Exception:
                continue
            if not isinstance(v, dict):
                continue
            cleaned[ck] = v
        self.sticky_data = cleaned

    def _save_data(self):
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.sticky_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ---------------- helpers ----------------
    def _ensure_channel_media(self, channel_id: str):
        path = os.path.join(self.media_dir, channel_id)
        os.makedirs(path, exist_ok=True)
        return path

    def _is_supported_image(self, attachment: discord.Attachment):
        name = attachment.filename or ""
        ext = os.path.splitext(name)[1].lower()
        if ext in SUPPORTED_EXTS:
            return True
        ctype = getattr(attachment, "content_type", "") or ""
        if ctype.startswith("image/"):
            return True
        return False

    async def _save_attachments(self, channel_id: str, message: discord.Message):
        if not message.attachments:
            return []
        out = []
        folder = self._ensure_channel_media(channel_id)
        idx = 1
        for att in message.attachments:
            if not self._is_supported_image(att):
                return None
            name = att.filename or f"{message.id}_{idx}"
            ext = os.path.splitext(name)[1].lower()
            if ext == "":
                ctype = getattr(att, "content_type", "") or ""
                if ctype.startswith("image/"):
                    ext = "." + ctype.split("/", 1)[1]
            if ext not in SUPPORTED_EXTS:
                return None
            local_name = f"{message.id}_{idx}{ext}"
            local_path = os.path.join(folder, local_name)
            try:
                await att.save(local_path)
                out.append(os.path.join(channel_id, local_name))  # relative path under media_dir
            except Exception:
                return None
            idx += 1
        return out

    async def _validate_existing(self, channel: discord.TextChannel, entry: dict):
        if not entry or not entry.get("active", False):
            return False
        mid = entry.get("sticky_message_id")
        if not mid:
            return False
        try:
            await channel.fetch_message(mid)
            return True
        except discord.NotFound:
            return False
        except Exception:
            # on ambiguous error be conservative and treat as existing to avoid accidental overwrite
            return True

    def _on_cooldown(self, channel_id: str) -> float:
        last = self._last_action.get(channel_id, 0.0)
        elapsed = time.monotonic() - last
        if elapsed < COOLDOWN_SECONDS:
            return COOLDOWN_SECONDS - elapsed
        return 0.0

    def _ensure_refresh_task(self, channel_id: str):
        """Start a background refresh task for this channel if not already running."""
        if channel_id in self._tasks:
            t = self._tasks[channel_id]
            if not t.done():
                return
        self._tasks[channel_id] = asyncio.create_task(self._refresh_cycle(channel_id))

    async def _refresh_cycle(self, channel_id: str):
        """Periodically ensure the sticky stays near the bottom of the channel."""
        interval = 30.0
        while True:
            entry = self.sticky_data.get(channel_id)
            if not entry or not entry.get("active", False):
                # stop when deactivated or removed
                break

            # fetch channel
            try:
                ch = self.bot.get_channel(int(channel_id))
                if ch is None:
                    ch = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                # deactivate on persistent failure
                entry["active"] = False
                self._save_data()
                break

            if not isinstance(ch, discord.TextChannel):
                entry["active"] = False
                self._save_data()
                break

            try:
                last_msg = None
                async for m in ch.history(limit=1):
                    last_msg = m
                    break

                sticky_msg_id = entry.get("sticky_message_id")

                # If the last message is already the sticky, just sleep and continue
                if last_msg is None or (sticky_msg_id and last_msg.id == sticky_msg_id):
                    await asyncio.sleep(interval)
                    continue

                # Delete old sticky message if present
                if sticky_msg_id:
                    try:
                        old_msg = await ch.fetch_message(sticky_msg_id)
                        await old_msg.delete()
                    except discord.NotFound:
                        pass
                    except Exception:
                        pass

                # Rebuild content and attachments from stored data
                desc = entry.get("content", "(no text)")
                # Bold + underlined header, normal-size text below
                content = f"__**Channel Sticky:**__\n{desc}"

                files = []
                rel_list = entry.get("attachments", []) or []
                if rel_list:
                    abs_paths = [os.path.join(self.media_dir, p) for p in rel_list]
                    file_objs = []
                    for p in abs_paths:
                        if os.path.exists(p):
                            try:
                                file_objs.append(discord.File(p, filename=os.path.basename(p)))
                            except Exception:
                                pass
                    if file_objs:
                        files = file_objs

                try:
                    new_msg = await ch.send(content=content, files=files)
                    entry["sticky_message_id"] = new_msg.id
                    entry["timestamp"] = iso_now()
                    self._save_data()
                except Exception:
                    # On send failure, just wait and retry later
                    pass

            except Exception:
                # unexpected error; do not crash the task, just wait
                pass

            await asyncio.sleep(interval)

    # ---------------- commands ----------------
    @commands.command(name="stick")
    async def stick(self, ctx: commands.Context, *, text: str = None):
        ch = ctx.channel
        # only allow in non-thread text channels
        if isinstance(ch, discord.Thread):
            emb = discord.Embed(description=" This command can only be used in a normal channel, not a thread.", color=discord.Color.red())
            await ctx.send(embed=emb)
            return

        channel_id = str(ch.id)
        # cooldown guard
        remaining = self._on_cooldown(channel_id)
        if remaining:
            emb = discord.Embed(description=f" Cooldown active. Try again in {int(remaining)}s.", color=discord.Color.red())
            await ctx.send(embed=emb)
            return

        # require either text or attachments
        if (not text or not text.strip()) and not ctx.message.attachments:
            emb = discord.Embed(description=" Provide text or attach an image to create a sticky.", color=discord.Color.red())
            await ctx.send(embed=emb)
            return

        async with self._lock:
            existing = self.sticky_data.get(channel_id)
            exists = await self._validate_existing(ch, existing)
            if exists:
                emb = discord.Embed(description=" This channel already has an active sticky. Use -unstick first to remove it.", color=discord.Color.red())
                await ctx.send(embed=emb)
                return

            # check attachments
            if ctx.message.attachments:
                for att in ctx.message.attachments:
                    if not self._is_supported_image(att):
                        emb = discord.Embed(description=" Unsupported attachment type. Supported: png, jpg, jpeg, gif, webp", color=discord.Color.red())
                        await ctx.send(embed=emb)
                        return

            saved = []
            if ctx.message.attachments:
                saved = await self._save_attachments(channel_id, ctx.message)
                if saved is None:
                    emb = discord.Embed(description=" Failed to save attachments or unsupported file present.", color=discord.Color.red())
                    await ctx.send(embed=emb)
                    return

            # build sticky message content (header + normal text)
            desc = text.strip() if text and text.strip() else "(no text)"
            content = f"__**Channel Sticky:**__\n{desc}"

            files = []
            if saved:
                abs_paths = [os.path.join(self.media_dir, p) for p in saved]
                file_objs = []
                for p in abs_paths:
                    if os.path.exists(p):
                        try:
                            file_objs.append(discord.File(p, filename=os.path.basename(p)))
                        except Exception:
                            pass
                if file_objs:
                    files = file_objs

            try:
                master = await ch.send(content=content, files=files)
            except discord.Forbidden:
                emb = discord.Embed(description=" Missing permission to send messages in this channel.", color=discord.Color.red())
                await ctx.send(embed=emb)
                return
            except Exception:
                emb = discord.Embed(description=" Failed to post sticky message.", color=discord.Color.red())
                await ctx.send(embed=emb)
                return

            # store entry
            self.sticky_data[channel_id] = {
                "channel_id": channel_id,
                "sticky_message_id": master.id,
                "original_message_id": ctx.message.id,
                "content": desc,
                "marked_by": ctx.author.display_name,
                "timestamp": iso_now(),
                "active": True,
                "attachments": saved or []
            }
            self._save_data()
            self._last_action[channel_id] = time.monotonic()

            # ensure background refresh task is running
            self._ensure_refresh_task(channel_id)

        emb = discord.Embed(description=" Sticky created for this channel.", color=discord.Color.green())
        await ctx.send(embed=emb)

    @commands.command(name="unstick")
    async def unstick(self, ctx: commands.Context):
        ch = ctx.channel
        if isinstance(ch, discord.Thread):
            emb = discord.Embed(description=" This command can only be used in a normal channel, not a thread.", color=discord.Color.red())
            await ctx.send(embed=emb)
            return

        channel_id = str(ch.id)
        remaining = self._on_cooldown(channel_id)
        if remaining:
            emb = discord.Embed(description=f" Cooldown active. Try again in {int(remaining)}s.", color=discord.Color.red())
            await ctx.send(embed=emb)
            return

        async with self._lock:
            entry = self.sticky_data.get(channel_id)
            if not entry or not entry.get("active", False):
                emb = discord.Embed(description=" No active sticky found in this channel.", color=discord.Color.red())
                await ctx.send(embed=emb)
                return

            mid = entry.get("sticky_message_id")
            if mid:
                try:
                    msg = await ch.fetch_message(mid)
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                except discord.NotFound:
                    pass
                except Exception:
                    # on ambiguous error continue to deactivate
                    pass

            # mark inactive and persist
            entry["active"] = False
            entry["timestamp"] = iso_now()
            self._save_data()
            self._last_action[channel_id] = time.monotonic()

            # cancel refresh task if running
            t = self._tasks.pop(channel_id, None)
            if t is not None:
                try:
                    t.cancel()
                except Exception:
                    pass

        emb = discord.Embed(description=" Sticky removed from this channel.", color=discord.Color.green())
        await ctx.send(embed=emb)

async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelSticky(bot))
