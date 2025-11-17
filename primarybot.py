#Insane amount of changes done, including directory adjustments for it to be compatible with pterodactly based linux vm's
#Further Updated it to be able to deactivate cogs as well
#little bit of chatgpt because it was rlly painful to get the directory working
#image support with stickies within embed
#@stickypins, -sticky, and -solution performing the same functions
#-deactivate to deactivate a particular thread when followed by a thread id within the parent id
#inbuilt image storage to make sure files are always avalible
#Last Version So far before release
# primarybot.py
import discord
from discord.ext import commands
import asyncio
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

# ------------- Config ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN not found in environment (.env)")

PARENT_CHANNEL_ID = [Forum ID]
OWNER_ID = [User ID of the host]
STICKY_MEDIA_DIR = "/home/container" #Folder Directory of sticky_media, this is where all images from threads are stored
DATA_FILE = os.path.join(os.path.dirname(STICKY_MEDIA_DIR), "stickydata.json") #Under testing, it has been observed that some linux vm's, particularly pterodactyl based host vm's have a problem where stickydata.json is duplicated, this is done to prevent any mismatch of the files
REFRESH_INTERVAL = 8.0 #The amount of time taken for each thread to check for new msgs and repost accordingly
BACKOFF_INTERVAL = 10.0 #The amount of time that is used as an interval when the bot is ratelimited, this temporarily replaces REFRESH_INTERVAL
MAX_AGE_DAYS = 30 #After a thread is older than n amount of days, it will automatically deactivate sticky reposting
LOG_LINES_LIMIT = 200 #Amount of lines dilsplayable by -console
CONSOLE_RETURN_LINES = 30 #Amount of lines displayable on one page of -console (in the case pagination is required)
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"} #All Supported formats for images in solution sticky

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

class StickyBot(commands.Bot):
    async def setup_hook(self):
        # load your deactivate cog here
        await self.load_extension("cogs.deactivate")


bot = StickyBot(command_prefix="-", intents=intents)

# ------------- Runtime state -------------
sticky_data = {}          # thread_id(str) -> entry dict
tasks = {}                # thread_id(str) -> asyncio.Task
locks = {}                # thread_id(str) -> asyncio.Lock
deactivated_threads = {}  # thread_id(str) -> bool (False = deactivated)
console_logs = []         # in-memory internal events (no timestamps/paths)

#So satisfying to make them all the comments allign hehe
# Expose core runtime dictionaries on the bot instance so cogs can access them via self.bot without importing primarybot as a module.
bot.sticky_data = sticky_data
bot.tasks = tasks
bot.deactivated_threads = deactivated_threads


# ------------- Helpers -------------
def log(line: str):
    clean = str(line).strip()
    console_logs.append(clean)
    if len(console_logs) > LOG_LINES_LIMIT:
        del console_logs[0 : len(console_logs) - LOG_LINES_LIMIT]
        # a
    print(clean)

def load_data():
    global sticky_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                sticky_data = json.load(f)
        except Exception as e:
            log(f"Failed to load {DATA_FILE}: {e}")
            sticky_data = {}
    else:
        sticky_data = {}
    # normalize keys as strings and validate structure minimally
    cleaned = {}
    for k, v in sticky_data.items():
        try:
            tk = str(int(k))
        except Exception:
            continue
        if not isinstance(v, dict):
            continue
        cleaned[tk] = v
    sticky_data = cleaned

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(sticky_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"Failed to save {DATA_FILE}: {e}")

def iso_now():
    return datetime.now(timezone.utc).isoformat()

def iso_to_dt(iso_str: str):
    try:
        return datetime.fromisoformat(iso_str)
    except Exception:
        return None

def ensure_media_dir(thread_id: str):
    path = os.path.join(STICKY_MEDIA_DIR, thread_id)
    os.makedirs(path, exist_ok=True)
    return path

def is_supported_image(attachment: discord.Attachment):
    # check by filename extension (fallback if content_type is None)
    name = attachment.filename or ""
    ext = os.path.splitext(name)[1].lower()
    if ext in SUPPORTED_EXTS:
        return True
    # also accept if content_type starts with image/
    ctype = getattr(attachment, "content_type", None) or ""
    if ctype.startswith("image/"):
        return True
    return False

def make_permission_denied_embed(command_name: str, user: discord.User):
    emb = discord.Embed(
        title="Permission Denied",
        description="You do not have permission to use this command.",
        color=discord.Color.red(),
    )
    emb.set_footer(text=f"for command [{command_name}] • requested by {user.name}")
    return emb

def make_solution_embed(content: str, asked_by_name: str):
    desc = content if content else "(no text)"
    emb = discord.Embed(title="💡 Solution To This Question!", description=desc, color=discord.Color.gold())
    emb.set_footer(text=f"Asked by {asked_by_name}")
    return emb
#lwk might wanna change these emoji's
def make_jump_view(guild_id: int, channel_id: int, message_id: int):
    view = discord.ui.View()
    url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    view.add_item(discord.ui.Button(label="Jump to Solution", url=url, style=discord.ButtonStyle.link))
    return view

# ---------------- New helper ----------------
def attachments_supported_and_list(message: discord.Message):
    """
    Check attachments on message.
    Returns (True, None) if ok (or no attachments).
    If any unsupported attachment found returns (False, error_embed).
    """
    if not message.attachments:
        return True, None

    unsupported_names = []
    for att in message.attachments:
        if not is_supported_image(att):
            unsupported_names.append(att.filename or "<unknown>")
    if unsupported_names:
        # build embed explaining unsupported files
        emb = discord.Embed(
            title="Unsupported attachment",
            description=(
                "Only image formats **png, jpg, jpeg, gif, webp** are supported for stickies.\n\n"
                "Unsupported file(s):\n" + "\n".join(f"- {n}" for n in unsupported_names)
            ),
            color=discord.Color.red()
        )
        return False, emb
    return True, None

# ------------- File utilities -------------
async def save_attachments_locally(thread_id: str, original_msg: discord.Message):
    """
    Save supported image attachments to sticky_media/<thread_id>/<original_msg_id>_<i>.<ext>
    Returns list of relative file paths (strings) (empty list if none).
    Returns None if saving failed or unsupported present (shouldn't happen if pre-checked).
    """
    out = []
    if not original_msg.attachments:
        return out

    folder = ensure_media_dir(thread_id)
    idx = 1
    for att in original_msg.attachments:
        if not is_supported_image(att):
            return None  # indicate unsupported file type present (should have been caught earlier)
        name = att.filename or f"{original_msg.id}_{idx}"
        ext = os.path.splitext(name)[1].lower()
        if ext == "":
            # find ext from content_type if possible
            ctype = getattr(att, "content_type", "") or ""
            if ctype.startswith("image/"):
                ext = "." + ctype.split("/", 1)[1]
        if ext not in SUPPORTED_EXTS:
            # double-check - if still unsupported, reject
            return None
        local_name = f"{original_msg.id}_{idx}{ext}"
        local_path = os.path.join(folder, local_name)
        try:
            await att.save(local_path)
            out.append(os.path.join(thread_id, local_name))  # store relative path under sticky_media
        except Exception as e:
            log(f"Failed to save attachment {att.filename}: {e}")
            return None
        idx += 1
    return out

def build_local_attachment_paths(thread_id: str, rel_paths):
    """Return absolute file paths from stored relative ones (under STICKY_MEDIA_DIR).
    This function will attempt the primary STICKY_MEDIA_DIR and also a likely alternative
    '/home/container/sticky_media' (useful for host environments)."""
    res = []
    # compute alternative media dir: one level up from STICKY_MEDIA_DIR parent + "sticky_media"
    # e.g. if STICKY_MEDIA_DIR = /home/container/StickyPins/sticky_media -> alt = /home/container/sticky_media
    alt_media_dir = os.path.normpath(os.path.join(os.path.dirname(STICKY_MEDIA_DIR), "..", "sticky_media"))

    for rel in rel_paths:
        # rel is stored like "<thread_id>/<filename>"
        primary_path = os.path.join(STICKY_MEDIA_DIR, rel)
        if os.path.exists(primary_path):
            res.append(primary_path)
            continue
        alt_path = os.path.join(alt_media_dir, rel)
        if os.path.exists(alt_path):
            res.append(alt_path)
            continue
        # if neither exists, still append primary (caller will log/open and handle failure)
        res.append(primary_path)
    return res

# ------------- Core operations -------------
async def create_sticky(thread: discord.Thread, original_msg: discord.Message, marker_name: str, pin_first_time=True):
    """
    Create sticky: save attachments locally (if present & supported), send embed + files,
    store DB entry and return sent message or None on failure.
    """
    # Save attachments locally (function also returns None on error)
    saved = []
    if original_msg.attachments:
        saved = await save_attachments_locally(str(thread.id), original_msg)
        if saved is None:
            # Unexpected error saving attachments; return failure
            emb = discord.Embed(
                title="Error saving attachments",
                description="There was an error saving one or more attachments. Sticky was not created.",
                color=discord.Color.red()
            )
            try:
                await original_msg.reply(embed=emb)
            except Exception:
                try:
                    await thread.send(embed=emb)
                except Exception:
                    pass
            return None

    # build embed
    emb = make_solution_embed(original_msg.content or "(no text)", original_msg.author.display_name)

    files = []
    # if we have saved local images, attach them to message and use first as embed image
    if saved:
        abs_paths = build_local_attachment_paths(str(thread.id), saved)
        # first file used as embed image (attachment://)
        # prepare discord.File objects with appropriate filename
        file_objs = []
        for p in abs_paths:
            try:
                filename = os.path.basename(p)
                file_objs.append(discord.File(p, filename=filename))
            except Exception as e:
                log(f"Failed to open saved file {p}: {e}")
        if file_objs:
            # set embed image to first file using attachment://filename
            emb.set_image(url=f"attachment://{file_objs[0].filename}")
            files = file_objs

    try:
        sent = await thread.send(embed=emb, files=files, view=make_jump_view(thread.guild.id, thread.id, original_msg.id))
    except discord.Forbidden:
        log(f"Missing permission to send sticky in thread {thread.id}")
        return None
    except Exception as e:
        log(f"Failed to send sticky in thread {thread.id}: {e}")
        return None

    if pin_first_time:
        try:
            await sent.pin()
        except Exception:
            pass

    tid_str = str(thread.id)

    # update DB (store relative attachment paths list)
    sticky_data[tid_str] = {
        "thread_id": tid_str,
        "sticky_message_id": sent.id,
        "original_message_id": original_msg.id,
        "content": original_msg.content or "",
        "marked_by": marker_name,
        "timestamp": iso_now(),
        "active": True,
        "attachments": saved or []  # list of relative paths under sticky_media/<thread_id>/...
    }
    # ensure this thread is marked active in the flag dict as well
    deactivated_threads[tid_str] = True
    save_data()
    log(f"Created sticky in thread {thread.name} ({thread.id}) by {marker_name}")
    return sent

async def delete_msg_if_exists(channel: discord.abc.Messageable, msg_id: int):
    try:
        msg = await channel.fetch_message(msg_id)
        await msg.delete()
    except (discord.NotFound, discord.Forbidden):
        return
    except Exception:
        return

async def refresh_cycle(thread_id_str: str):
    lock = locks.setdefault(thread_id_str, asyncio.Lock())
    interval = REFRESH_INTERVAL
    while True:
        # check global deactivation flag first
        entry = sticky_data.get(thread_id_str)
        if not entry or entry.get("active") is False:
            log(f"Stopping refresh task for thread {thread_id_str} (inactive)")
            break

        entry = sticky_data.get(thread_id_str)
        if not entry or not entry.get("active", False):
            log(f"Stopping refresh task for thread {thread_id_str} (inactive/missing)")
            break

        try:
            thread = await bot.fetch_channel(int(thread_id_str))
            if not isinstance(thread, discord.Thread):
                log(f"Thread {thread_id_str} not a thread; deactivating")
                entry["active"] = False
                save_data()
                break
        except Exception:
            log(f"Could not fetch thread {thread_id_str}; deactivating")
            entry["active"] = False
            save_data()
            break

        async with lock:
            try:
                last_msg = None
                async for m in thread.history(limit=1):
                    last_msg = m
                    break

                sticky_msg_id = entry.get("sticky_message_id")
                if last_msg is None or last_msg.id == sticky_msg_id:
                    await asyncio.sleep(interval)
                    continue

                # need to repost: delete old sticky message
                if sticky_msg_id:
                    await delete_msg_if_exists(thread, sticky_msg_id)

                # build embed from stored content and re-attach local files
                emb = make_solution_embed(entry.get("content", "(no text)"), entry.get("marked_by", "Unknown"))
                files = []
                rel_list = entry.get("attachments", []) or []
                if rel_list:
                    abs_paths = build_local_attachment_paths(thread_id_str, rel_list)
                    file_objs = []
                    for p in abs_paths:
                        if os.path.exists(p):
                            try:
                                filename = os.path.basename(p)
                                file_objs.append(discord.File(p, filename=filename))
                            except Exception as e:
                                log(f"Failed to attach file {p}: {e}")
                    if file_objs:
                        emb.set_image(url=f"attachment://{file_objs[0].filename}")
                        files = file_objs

                try:
                    new_msg = await thread.send(embed=emb, files=files, view=make_jump_view(thread.guild.id, thread.id, entry.get("original_message_id")))
                    # do NOT pin when reposting to avoid pin spam
                    entry["sticky_message_id"] = new_msg.id
                    entry["timestamp"] = iso_now()
                    save_data()
                    log(f"Reposted sticky in thread {thread.name} ({thread.id})")
                except discord.HTTPException as he:
                    # backoff on rate-limit
                    if getattr(he, "status", None) == 429:
                        log(f"Rate limited while reposting in {thread.id}; backing off")
                        interval = BACKOFF_INTERVAL
                    else:
                        log(f"HTTP error while reposting in {thread.id}: {he}")
                except Exception as e:
                    log(f"Failed to repost sticky in {thread.id}: {e}")

            except discord.Forbidden:
                log(f"No permission to read history in thread {thread_id_str}; stopping task")
                entry["active"] = False
                save_data()
                break
            except Exception as e:
                log(f"Unexpected error in refresh task for {thread_id_str}: {e}")

        await asyncio.sleep(interval)
        if interval != REFRESH_INTERVAL:
            interval = REFRESH_INTERVAL

# ------------- Confirmation helper (embeds + reactions) -------------
async def ask_replace_confirmation(author: discord.Member):
    emb = discord.Embed(
        title="Confirm Sticky Replacement",
        description="⚠️ You are about to replace the existing sticky in the thread.\n\nReact with ✅ to confirm or ❌ to cancel.",
        color=discord.Color.orange(),
    )
    try:
        prompt = await author.send(embed=emb)
    except Exception:
        return False
    # add reactions
    try:
        await prompt.add_reaction("✅")
        await prompt.add_reaction("❌")
    except Exception:
        # if reactions fail, fallback to text response in DM
        pass

    def check(reaction, user):
        return user == author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == prompt.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", check=check, timeout=60.0)
        if str(reaction.emoji) == "✅":
            confirm_emb = discord.Embed(description="✅ Confirmed. Replacing sticky now.", color=discord.Color.green())
            await author.send(embed=confirm_emb)
            return True
        else:
            cancel_emb = discord.Embed(description="❎ Cancelled Sticky Replacement.", color=discord.Color.red())
            await author.send(embed=cancel_emb)
            return False
    except asyncio.TimeoutError:
        timeout_emb = discord.Embed(description="⌛ Confirmation timed out. Your Sticky Replace Request has been Cancellled. Try Replacing the sticky again and react to the confirmation message within 10 seconds!.", color=discord.Color.red())
        await author.send(embed=timeout_emb)
        return False

# ------------- Events & commands -------------
@bot.event
async def on_ready():
    load_data()
    # set presence (Playing)
    try:
        activity = discord.Activity(type=discord.ActivityType.playing, name='Run "-sticky" in the help thread!')
        await bot.change_presence(activity=activity)
    except Exception:
        pass

    log(f"Bot ready as {bot.user}")
    # resume active stickies newest -> oldest
    items = []
    for tid, entry in sticky_data.items():
        ts = entry.get("timestamp")
        dt = iso_to_dt(ts) if ts else None
        items.append((tid, dt or datetime(1970, 1, 1, tzinfo=timezone.utc)))
    items.sort(key=lambda x: x[1], reverse=True)

    resumed = 0
    skipped = 0
    for tid, dt in items:
        entry = sticky_data.get(tid)
        if not entry or not entry.get("active", True):
            continue
        age = datetime.now(timezone.utc) - (iso_to_dt(entry.get("timestamp")) or datetime.now(timezone.utc))
        if age > timedelta(days=MAX_AGE_DAYS):
            entry["active"] = False
            save_data()
            skipped += 1
            log(f"⏳ Skipped old sticky (>{MAX_AGE_DAYS}d) for thread {tid}")
            continue

        try:
            thread = await bot.fetch_channel(int(tid))
        except Exception:
            entry["active"] = False
            save_data()
            log(f"Could not fetch thread {tid}; deactivated sticky")
            continue

        if not isinstance(thread, discord.Thread) or (thread.parent_id != PARENT_CHANNEL_ID):
            entry["active"] = False
            save_data()
            log(f"Sticky thread {tid} not in parent channel; deactivated")
            continue

        # delete old sticky message if present
        old_id = entry.get("sticky_message_id")
        if old_id:
            await delete_msg_if_exists(thread, old_id)

        # recreate sticky message (do not pin to avoid pin spam on restart)
        try:
            emb = make_solution_embed(entry.get("content", "(no text)"), entry.get("marked_by", "Unknown"))
            files = []
            rel_list = entry.get("attachments", []) or []
            if rel_list:
                abs_paths = build_local_attachment_paths(tid, rel_list)
                file_objs = []
                for p in abs_paths:
                    if os.path.exists(p):
                        try:
                            file_objs.append(discord.File(p, filename=os.path.basename(p)))
                        except Exception as e:
                            log(f"Failed to attach saved file {p}: {e}")
                if file_objs:
                    emb.set_image(url=f"attachment://{file_objs[0].filename}")
                    files = file_objs
            new_msg = await thread.send(embed=emb, files=files, view=make_jump_view(thread.guild.id, thread.id, entry.get("original_message_id")))
            entry["sticky_message_id"] = new_msg.id
            entry["timestamp"] = iso_now()
            save_data()
            tasks[tid] = asyncio.create_task(refresh_cycle(tid))
            resumed += 1
            log(f"♻️ Resumed sticky for thread {thread.name} ({tid})")
        except Exception as e:
            entry["active"] = False
            save_data()
            log(f"Failed to resume sticky for thread {tid}: {e}")

    log(f"✅ Resume complete: {resumed} resumed, {skipped} skipped")

# ignore CommandNotFound logs by handling quietly
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    # otherwise re-raise so it can appear normally in logs
    raise error

# command aliases: -sticky and -solution do same
@bot.command(name="sticky", aliases=["solution"])
async def sticky_cmd(ctx):
    # convenience wrapper: behave like reply-based -sticky
    # ensure allowed channel (must be in a thread under parent)
    ch = ctx.channel
    if not isinstance(ch, discord.Thread) or ch.parent_id != PARENT_CHANNEL_ID:
        emb = discord.Embed(description="❌ This command can only be used inside a thread within the Help channel!", color=discord.Color.red())
        return await ctx.send(embed=emb)
    # must be used as a reply
    if not ctx.message.reference:
        emb = discord.Embed(description="❌ Reply to the message you want to mark as solution using this command.", color=discord.Color.red())
        return await ctx.send(embed=emb)
    try:
        replied = await ch.fetch_message(ctx.message.reference.message_id)
    except Exception:
        emb = discord.Embed(description="❌ Could not fetch the replied message. Make sure its not deleted!", color=discord.Color.red())
        return await ctx.send(embed=emb)

    # ---- pre-check attachments ----
    ok, err_emb = attachments_supported_and_list(replied)
    if not ok:
        # send error embed and do NOT sticky
        return await ctx.send(embed=err_emb)

    tid = str(ch.id)
    existing = sticky_data.get(tid)
    if existing and existing.get("active", False):
        ok_confirm = await ask_replace_confirmation(ctx.author)
        if not ok_confirm:
            emb = discord.Embed(description="❎ Sticky replacement cancelled.", color=discord.Color.red())
            return await ctx.send(embed=emb)
        old_id = existing.get("sticky_message_id")
        if old_id:
            await delete_msg_if_exists(ch, old_id)

    created = await create_sticky(ch, replied, ctx.author.display_name, pin_first_time=True)
    if created:
        if tid in tasks:
            try:
                tasks[tid].cancel()
            except Exception:
                pass
        tasks[tid] = asyncio.create_task(refresh_cycle(tid))
        emb = discord.Embed(description="✅ Sticky created and pinned.", color=discord.Color.green())
        return await ctx.send(embed=emb)
    else:
        emb = discord.Embed(description="❌ Failed to create sticky. Check if your image is not supported by discord, Otherwise, permissions may be denied.", color=discord.Color.red())
        return await ctx.send(embed=emb)

@bot.event
async def on_message(message: discord.Message):
    # process commands first for prefix commands
    await bot.process_commands(message)

    if message.author.bot:
        return

    content = message.content.strip()
    ch = message.channel

    # Permission protected commands (deny embed)
    if content in ("-sd", "-console") and message.author.id != OWNER_ID:
        emb = make_permission_denied_embed(content, message.author)
        try:
            await message.channel.send(embed=emb)
        except Exception:
            pass
        return

    # Owner shutdown
    if content == "-sd" and message.author.id == OWNER_ID:
        emb = discord.Embed(description="✌ Shutting down. cya!", color=discord.Color.red())
        try:
            await message.channel.send(embed=emb)
        except Exception:
            pass
        log("🟥 Manual shutdown initiated by owner.")
        for t in list(tasks.values()):
            try:
                t.cancel()
            except Exception:
                pass
        save_data()
        await bot.close()
        return

    # Owner console
    if content == "-console" and message.author.id == OWNER_ID:
        lines = console_logs[-CONSOLE_RETURN_LINES:]
        desc = "\n".join(lines) if lines else "No internal events yet."
        emb = discord.Embed(title="Console (Internal Events)", description=desc, color=discord.Color.blurple())
        try:
            await message.author.send(embed=emb)
        except Exception:
            pass
        return

    # If bot is pinged anywhere (only valid behavior inside parent threads)
    if bot.user.mentioned_in(message):
        # if not in relevant thread -> send permission/usage embed in-channel
        if not isinstance(ch, discord.Thread) or ch.parent_id != PARENT_CHANNEL_ID:
            # if ping outside allowed area, politely ignore (or optionally reply)
            return

        # If ping is a reply -> create sticky from replied message
        if message.reference:
            try:
                replied = await ch.fetch_message(message.reference.message_id)
            except Exception:
                emb = discord.Embed(description="❌ Could not fetch the replied message.", color=discord.Color.red())
                await message.channel.send(embed=emb)
                return

            # ---- pre-check attachments ----
            ok, err_emb = attachments_supported_and_list(replied)
            if not ok:
                # send error embed and do NOT sticky
                try:
                    await message.reply(embed=err_emb, mention_author=False)
                except Exception:
                    await message.channel.send(embed=err_emb)
                return

            tid = str(ch.id)
            existing = sticky_data.get(tid)
            if existing and existing.get("active", False):
                ok_confirm = await ask_replace_confirmation(message.author)
                if not ok_confirm:
                    emb = discord.Embed(description="❎ Sticky replacement cancelled.", color=discord.Color.red())
                    await message.reply(embed=emb)
                    return
                old_id = existing.get("sticky_message_id")
                if old_id:
                    await delete_msg_if_exists(ch, old_id)

            created = await create_sticky(ch, replied, message.author.display_name, pin_first_time=True)
            if created:
                if tid in tasks:
                    try:
                        tasks[tid].cancel()
                    except Exception:
                        pass
                tasks[tid] = asyncio.create_task(refresh_cycle(tid))
                emb = discord.Embed(description="✅ Sticky created and pinned.", color=discord.Color.green())
                await message.reply(embed=emb, mention_author=False)
            else:
                emb = discord.Embed(description="❌ Failed to create sticky. Check if your image is not supported by discord, Otherwise, permissions may be denied.", color=discord.Color.red())
                await message.reply(embed=emb, mention_author=False)
            return
        else:
            # ping without reply -> instruct user to reply while pinging
            emb = discord.Embed(
                title="Reply to the sticky message when pinging me!",
                description="You must reply to the message you want to mark as a solution when pinging the bot.",
                color=discord.Color.red()
            )
            emb.set_footer(text="Use by replying to a message with @StickyPins")
            await message.channel.send(embed=emb)
            return

    # Only proceed with thread-only command logic for threads in parent channel
    if not isinstance(ch, discord.Thread) or ch.parent_id != PARENT_CHANNEL_ID:
        return

    # -sticky typed as plain message (reply usage)
    if content == "-sticky" and message.reference:
        try:
            replied = await ch.fetch_message(message.reference.message_id)
        except Exception:
            emb = discord.Embed(description="❌ Could not fetch the replied message.", color=discord.Color.red())
            await message.reply(embed=emb)
            return

        # ---- pre-check attachments ----
        ok, err_emb = attachments_supported_and_list(replied)
        if not ok:
            # send error embed and do NOT sticky
            await message.reply(embed=err_emb)
            return

        tid = str(ch.id)
        existing = sticky_data.get(tid)
        if existing and existing.get("active", False):
            ok_confirm = await ask_replace_confirmation(message.author)
            if not ok_confirm:
                emb = discord.Embed(description="❎ Sticky replacement cancelled.", color=discord.Color.red())
                await message.reply(embed=emb)
                return
            old_id = existing.get("sticky_message_id")
            if old_id:
                await delete_msg_if_exists(ch, old_id)

        created = await create_sticky(ch, replied, message.author.display_name, pin_first_time=True)
        if created:
            if tid in tasks:
                try:
                    tasks[tid].cancel()
                except Exception:
                    pass
            tasks[tid] = asyncio.create_task(refresh_cycle(tid))
            emb = discord.Embed(description="✅ Sticky created and pinned.", color=discord.Color.green())
            await message.reply(embed=emb)
        else:
            emb = discord.Embed(description="❌ Failed to create sticky. Check if your image is not supported by discord, Otherwise, permissions may be denied.", color=discord.Color.red())
            await message.reply(embed=emb)
        return

# ------------- Run -------------
if __name__ == "__main__":
    load_data()
    # ensure media dir exists (primary)
    os.makedirs(STICKY_MEDIA_DIR, exist_ok=True)
    # ensure likely alternate media dir exists too (helps host environment /home/container/sticky_media)
    alt_media_dir = os.path.normpath(os.path.join(os.path.dirname(STICKY_MEDIA_DIR), "..", "sticky_media"))
    try:
        os.makedirs(alt_media_dir, exist_ok=True)
    except Exception:
        # non-fatal; just continue
        pass
    bot.run(TOKEN)
