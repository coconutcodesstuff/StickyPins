#TODO - Add json dir for storing stickied msgs
#TODO - Add a permission denied embed msg cuz it looks good
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from dotenv import load_dotenv
from typing import Dict, Optional

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_IDS = (1202369414721450005, 872007660587876372, 800570889082765323)  # Mod Discord id for shut down cmd

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
intents.typing = False
intents.presences = False

bot = commands.Bot(command_prefix="$", intents=intents)
sticky_messages: Dict[int, int] = {}  # {thread_id: message_id}
sticky_tasks: Dict[int, asyncio.Task] = {}  # Store tasks for cleanup


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"❌ Slash command sync failed: {e}")

    await bot.change_presence(activity=discord.Game(name="Keeping solutions sticky!"))


@bot.event
async def on_thread_delete(thread: discord.Thread):
    """Cleanup when a thread is deleted"""
    if thread.id in sticky_messages:
        del sticky_messages[thread.id]
    if thread.id in sticky_tasks:
        sticky_tasks[thread.id].cancel()
        del sticky_tasks[thread.id]


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Only trigger if the bot is pinged in a reply (inside a thread)
    if bot.user.mentioned_in(message) and message.reference and isinstance(message.channel, discord.Thread):
        thread = message.channel
        try:
            replied_msg = await thread.fetch_message(message.reference.message_id)
            
            if not replied_msg.content and not replied_msg.embeds:
                await message.reply("❌ Cannot mark an empty message as solution!", mention_author=False)
                return

            # Prevent double execution of msgs
            await asyncio.sleep(0.5)

            # If there's already a sticky message, then ask for a overide
            if thread.id in sticky_messages:
                try:
                    prev_sticky_id = sticky_messages[thread.id]
                    await thread.fetch_message(prev_sticky_id)  # Confirm the msgs existence
                    await ask_override_confirmation(message.author, thread, replied_msg)
                    return
                except discord.NotFound:
                    pass  # if there isnt then dont let the user continue and make a new sticky

            await create_sticky_message(thread, replied_msg, message.author)
            await message.reply("✅ Solution has been marked and pinned to the bottom!", mention_author=False)

        except discord.NotFound:
            await message.reply("❌ Could not find the message you replied to!", mention_author=False)
        except discord.Forbidden:
            await message.reply("❌ I don't have permission to manage messages in this thread!", mention_author=False) # quite self explanatory i think
        except Exception as e:
            print(f"Error in on_message: {e}")
            await message.reply("❌ An error occurred while processing your request.", mention_author=False)

    await bot.process_commands(message)


async def create_sticky_message(thread: discord.Thread, replied_msg: discord.Message, author: discord.Member) -> Optional[discord.Message]:
    """Creates a new sticky message and starts its manager"""
    try:
        # Create the sticky embed
        embed = create_solution_embed(replied_msg.content, author)
        
        # Create jump button
        view = discord.ui.View()
        jump_button = discord.ui.Button(label="Jump to Solution", url=replied_msg.jump_url, style=discord.ButtonStyle.link)
        view.add_item(jump_button)

        sticky = await thread.send(embed=embed, view=view)
        sticky_messages[thread.id] = sticky.id

        # Cancel existing task if any
        if thread.id in sticky_tasks:
            sticky_tasks[thread.id].cancel()

        # Create new task
        task = bot.loop.create_task(sticky_manager(thread, sticky, replied_msg, author))
        sticky_tasks[thread.id] = task
        
        return sticky
    except Exception as e:
        print(f"Error creating sticky message: {e}")
        return None


def create_solution_embed(content: str, author: discord.Member) -> discord.Embed:
    """Creates the solution embed"""
    description = content[:4000] if len(content) > 4000 else content  # Discord embed description limit
    embed = discord.Embed(
        title="💡 **Solution Message**",
        description=f"**The solution to this problem is:**\n\n{description}",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Marked by {author.display_name}")
    return embed


async def sticky_manager(thread: discord.Thread, sticky_msg: discord.Message, replied_msg: discord.Message, author: discord.Member):
    """Keeps the sticky message at the bottom of the thread."""
    try:
        await asyncio.sleep(2)
        while True:
            await asyncio.sleep(1)
            try:
                last_msg = None
                async for msg in thread.history(limit=1):
                    last_msg = msg
                if not last_msg:
                    continue

                if last_msg.id != sticky_msg.id:
                    # Delete old sticky
                    try:
                        await sticky_msg.delete()
                    except discord.NotFound:
                        pass

                    # Resend sticky with same content
                    new_msg = await create_sticky_message(thread, replied_msg, author)
                    if new_msg:
                        sticky_msg = new_msg
            except discord.NotFound:
                # Thread was deleted
                break
            except discord.Forbidden:
                print(f"Lost permissions in thread {thread.name}")
                break
            except Exception as e:
                print(f"Sticky loop error in {thread.name}: {e}")
                await asyncio.sleep(5)  # Back off on error
    finally:
        # Cleanup
        if thread.id in sticky_tasks:
            del sticky_tasks[thread.id]


async def ask_override_confirmation(user: discord.Member, thread: discord.Thread, new_replied_msg: discord.Message):
    """DMs the user asking to confirm sticky override."""
    try:
        dm = await user.create_dm()
        embed = discord.Embed(
            title="⚠️ Override Confirmation",
            description=(
                f"You are about to override the current solution in **{thread.name}**.\n\n"
                "If this is unintentional or incorrect, click **No**.\n"
                "Otherwise, press **Yes** to confirm."
            ),
            color=discord.Color.orange()
        )

        yes_button = discord.ui.Button(label="Yes", style=discord.ButtonStyle.danger)
        no_button = discord.ui.Button(label="No", style=discord.ButtonStyle.secondary)

        async def yes_callback(interaction: discord.Interaction):
            if interaction.user.id != user.id:
                await interaction.response.send_message("❌ You can't press this button.", ephemeral=True)
                return

            await interaction.response.send_message("✅ Overriding existing solution...", ephemeral=True)

            # Delete old sticky
            try:
                old_sticky_id = sticky_messages.get(thread.id)
                if old_sticky_id:
                    old_msg = await thread.fetch_message(old_sticky_id)
                    await old_msg.delete()
            except Exception:
                pass

            await create_sticky_message(thread, new_replied_msg, user)
            await dm.send("✅ Successfully overridden the existing solution.")

        async def no_callback(interaction: discord.Interaction):
            if interaction.user.id == user.id:
                await interaction.response.send_message("❎ Cancelled override.", ephemeral=True)

        yes_button.callback = yes_callback
        no_button.callback = no_callback

        view = discord.ui.View(timeout=60)  # 60 second timeout
        view.add_item(yes_button)
        view.add_item(no_button)

        confirmation_message = await dm.send(embed=embed, view=view)

        # Disable buttons after timeout
        await asyncio.sleep(60)
        for item in view.children:
            item.disabled = True
        await confirmation_message.edit(view=view)

    except discord.Forbidden:
        await thread.send(f"{user.mention}, I couldn't DM you for confirmation. Please enable DMs.", delete_after=8)


@bot.tree.command(name="sd", description="Shuts down the bot (owner only).")
async def shutdown(interaction: discord.Interaction):
    if interaction.user.id not in OWNER_IDS:
        await interaction.response.send_message("❌ You are not authorized to do this.", ephemeral=True)
        return

    await interaction.response.send_message("🛑 Shutting down StickyPins bot...", ephemeral=True)
    print("Bot manually shut down by owner.")
    
    # Cancel all sticky tasks
    for task in sticky_tasks.values():
        task.cancel()
    
    await bot.close()



bot.run(TOKEN)
