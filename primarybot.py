# Rewrote everything with the help of my brain and a little gpt cuz it was lwk kinda ahh before
# Called @bot.event 2 times even though I know its not best practice and the activity doesnt work because of it
# Got the JSON db system working
# Was too lazy to label the code, but it works!

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



PARENT_CHANNEL_ID = #[Channel Id of the Channel that will contain multiple threads within it]
OWNER_ID = #[User ID of whoever is running the bot]
DATA_FILE = "stickydata.json"
REFRESH_INTERVAL = 8.0
BACKOFF_INTERVAL = 10.0
MAX_AGE_DAYS = 30 #Can Be Adjusted
LOG_LINES_LIMIT = 200 #Maximum lines allowed for console commands in total i think. i kinda forgot what i set it to
CONSOLE_RETURN_LINES = 30 #yeah maximum return lines on one page

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="-", intents=intents)

#--------------Bot.Event------------------
@bot.event
async def on_ready():
    activity = discord.Activity(
        type=discord.ActivityType.playing,
        name='Run "-sticky" in the help thread!'
    )
    await bot.change_presence(activity=activity)
    print(f"✅ Logged in as {bot.user}")

# ------------- Runtime state -------------
sticky_data = {}
tasks = {}
locks = {}
console_logs = []


# ------------- Helpers -------------
def log(line: str):
    clean = str(line).strip()
    console_logs.append(clean)
    if len(console_logs) > LOG_LINES_LIMIT:
        del console_logs[0 : len(console_logs) - LOG_LINES_LIMIT]
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


# ------------- Embed Builders -------------
def make_solution_embed(content: str, asked_by_name: str):
    desc = content if content else "(no text)"
    emb = discord.Embed(
        title="Solution To This Question", description=desc, color=discord.Color.gold()
    )
    emb.set_footer(text=f"Asked by {asked_by_name}")
    return emb


def make_jump_view(guild_id: int, channel_id: int, message_id: int):
    view = discord.ui.View()
    url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    view.add_item(discord.ui.Button(label="Jump to Solution", url=url, style=discord.ButtonStyle.link))
    return view


def make_permission_denied_embed(command_name: str, user: discord.User):
    emb = discord.Embed(
        title="Permission Denied",
        description="You do not have permission to use this command!",
        color=discord.Color.red(),
    )
    emb.set_footer(text=f"for command [{command_name}] • requested by {user.name}")
    return emb


# ------------- Core -------------
async def create_sticky(thread: discord.Thread, original_msg: discord.Message, marker_name: str, pin_first_time=True):
    emb = make_solution_embed(original_msg.content or "(no text)", original_msg.author.display_name)
    view = make_jump_view(thread.guild.id, thread.id, original_msg.id)
    try:
        sent = await thread.send(embed=emb, view=view)
    except Exception as e:
        log(f"Failed to send sticky: {e}")
        return None

    if pin_first_time:
        try:
            await sent.pin()
        except Exception:
            pass

    sticky_data[str(thread.id)] = {
        "thread_id": str(thread.id),
        "sticky_message_id": sent.id,
        "original_message_id": original_msg.id,
        "content": original_msg.content or "",
        "marked_by": marker_name,
        "timestamp": iso_now(),
        "active": True,
    }
    save_data()
    return sent


async def delete_msg_if_exists(channel: discord.abc.Messageable, msg_id: int):
    try:
        msg = await channel.fetch_message(msg_id)
        await msg.delete()
    except Exception:
        return


async def refresh_cycle(thread_id_str: str):
    lock = locks.setdefault(thread_id_str, asyncio.Lock())
    interval = REFRESH_INTERVAL
    while True:
        entry = sticky_data.get(thread_id_str)
        if not entry or not entry.get("active", False):
            break
        async with lock:
            try:
                thread = await bot.fetch_channel(int(thread_id_str))
            except Exception:
                entry["active"] = False
                save_data()
                break

            async for m in thread.history(limit=1):
                last_msg = m
                break
            else:
                last_msg = None

            sticky_msg_id = entry.get("sticky_message_id")
            if last_msg is None or last_msg.id == sticky_msg_id:
                await asyncio.sleep(interval)
                continue

            if sticky_msg_id:
                await delete_msg_if_exists(thread, sticky_msg_id)

            emb = make_solution_embed(entry.get("content", "(no text)"), entry.get("marked_by", "Unknown"))
            view = make_jump_view(thread.guild.id, thread.id, entry.get("original_message_id"))
            try:
                new_msg = await thread.send(embed=emb, view=view)
                entry["sticky_message_id"] = new_msg.id
                entry["timestamp"] = iso_now()
                save_data()
            except Exception as e:
                log(f"Repost error: {e}")
        await asyncio.sleep(interval)


# ------------- Confirmation helper (now in embeds) -------------
async def ask_replace_confirmation(author: discord.Member):
    emb = discord.Embed(
        title="Confirm Sticky Replacement",
        description="⚠️ You are about to replace a sticky that already exists in a thread.\n\nReact with ✅ to confirm or ❌ to cancel.",
        color=discord.Color.orange(),
    )
    try:
        msg = await author.send(embed=emb)
    except Exception:
        return False
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

    def check(reaction, user):
        return user == author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id

    try:
        reaction, _ = await bot.wait_for("reaction_add", check=check, timeout=60.0)
        if str(reaction.emoji) == "✅":
            confirm_emb = discord.Embed(description="✅ Replacing the sticky!", color=discord.Color.green())
            await author.send(embed=confirm_emb)
            return True
        else:
            cancel_emb = discord.Embed(description="❎ Cancelled Sticky Change Request!", color=discord.Color.red())
            await author.send(embed=cancel_emb)
            return False
    except asyncio.TimeoutError:
        timeout_emb = discord.Embed(description="⌛ Confirmation timed out. Request Cancelled.", color=discord.Color.red())
        await author.send(embed=timeout_emb)
        return False


# ------------- Events -------------
@bot.event
async def on_ready():
    load_data()
    print(f"✅ Logged in as {bot.user}")
    # resume all stickies
    for tid, entry in sticky_data.items():
        if not entry.get("active", True):
            continue
        try:
            thread = await bot.fetch_channel(int(tid))
            if not isinstance(thread, discord.Thread):
                continue
            emb = make_solution_embed(entry.get("content", "(no text)"), entry.get("marked_by", "Unknown"))
            view = make_jump_view(thread.guild.id, thread.id, entry.get("original_message_id"))
            msg = await thread.send(embed=emb, view=view)
            entry["sticky_message_id"] = msg.id
            entry["timestamp"] = iso_now()
            save_data()
            tasks[tid] = asyncio.create_task(refresh_cycle(tid))
        except Exception as e:
            log(f"Failed to resume sticky {tid}: {e}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()
    ch = message.channel

    # --- Permission-protected commands ---
    if content in ("-sd", "-console"):
        if message.author.id != OWNER_ID:
            emb = make_permission_denied_embed(content, message.author)
            await message.channel.send(embed=emb)
            return

    # --- Shutdown (embed) ---
    if content == "-sd" and message.author.id == OWNER_ID:
        emb = discord.Embed(description="🛑 Shutting down.", color=discord.Color.red())
        await message.channel.send(embed=emb)
        save_data()
        for t in list(tasks.values()):
            try:
                t.cancel()
            except Exception:
                pass
        await bot.close()
        return

    # --- Console ---
    if content == "-console" and message.author.id == OWNER_ID:
        lines = console_logs[-CONSOLE_RETURN_LINES:]
        desc = "\n".join(lines) if lines else "No internal events yet."
        emb = discord.Embed(title="Console (Internal Events)", description=desc, color=discord.Color.blurple())
        await message.author.send(embed=emb)
        return

    # --- Only threads inside parent ---
    if not isinstance(ch, discord.Thread) or ch.parent_id != PARENT_CHANNEL_ID:
        await bot.process_commands(message)
        return

    # --- Sticky creation ---
    if content == "-sticky" and message.reference:
        try:
            replied = await ch.fetch_message(message.reference.message_id)
        except Exception:
            emb = discord.Embed(description="❌ Could not find the replied message. Make sure your replying to a message while running the command", color=discord.Color.red())
            await message.reply(embed=emb)
            return

        tid = str(ch.id)
        existing = sticky_data.get(tid)
        if existing and existing.get("active", False):
            ok = await ask_replace_confirmation(message.author)
            if not ok:
                emb = discord.Embed(description="❎ Sticky replacement cancelled.", color=discord.Color.red())
                await message.reply(embed=emb)
                return
            old_id = existing.get("sticky_message_id")
            if old_id:
                await delete_msg_if_exists(ch, old_id)

        created = await create_sticky(ch, replied, message.author.display_name)
        if created:
            if tid in tasks:
                tasks[tid].cancel()
            tasks[tid] = asyncio.create_task(refresh_cycle(tid))
            emb = discord.Embed(description="✅ Sticky created and pinned.", color=discord.Color.green())
            await message.reply(embed=emb)
        else:
            emb = discord.Embed(description="❌ Failed to create sticky.", color=discord.Color.red())
            await message.reply(embed=emb)

    await bot.process_commands(message)


# ------------- Run -------------
if __name__ == "__main__":
    load_data()
    bot.run(TOKEN)

