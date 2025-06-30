# main.py
import discord
from discord.commands import SlashCommandGroup, Option
from discord.ext import commands
import os
import sqlite3
from dotenv import load_dotenv

# Import our new platform tools from platforms.py
from platforms import get_platform_handler, platform_handlers

# --- BOT SETUP ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Bot(intents=intents)

# --- HELPER FUNCTIONS ---
def get_db_connection():
    """Connects to the SQLite database."""
    conn = sqlite3.connect('suno_contests.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- UI VIEWS (for confirmations) ---
class ConfirmationView(discord.ui.View):
    """A view with Confirm and Cancel buttons for deletion actions."""
    def __init__(self, author_id: int):
        super().__init__(timeout=30.0)
        self.value = None
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the original command user to interact
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        self.stop() # Stop listening for interactions

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        self.stop()

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    """Event that runs when the bot is connected and ready."""
    print(f'{bot.user} has connected to Discord!')
    print('Bot is ready and listening for commands.')

# --- COMMAND GROUPS ---
contest = SlashCommandGroup("contest", "Commands for managing Suno contests")
submission_group = SlashCommandGroup("submission", "Commands for managing your submissions")

# --- CONTEST MANAGEMENT COMMANDS (Admin Only) ---

@contest.command(name="create", description="Create a new music contest")
@commands.has_permissions(administrator=True)
async def create_contest(
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "A unique ID for the contest (e.g., 'summer2025')"),
    public_channel: Option(discord.TextChannel, "The public channel for voting"),
    review_channel: Option(discord.TextChannel, "The private channel for admin review"),
    allowed_platforms: Option(str, "Comma-separated list (e.g., 'suno,youtube')", required=False, default=None),
    submission_limit: Option(int, "Max submissions per user (default is 1)", required=False, default=1)
):
    """Admin command to create a contest, with platform and submission limits."""
    conn = get_db_connection()
    try:
        platform_str = None
        if allowed_platforms:
            valid_platforms = [p.name.lower() for p in platform_handlers]
            platforms_list = [p.strip().lower() for p in allowed_platforms.split(',')]
            if not all(p in valid_platforms for p in platforms_list):
                await ctx.respond(f"❌ Invalid platform name. Valid options are: {', '.join(valid_platforms)}", ephemeral=True)
                conn.close()
                return
            platform_str = ",".join(platforms_list)

        conn.execute(
            "INSERT INTO contests (contest_id, public_channel_id, review_channel_id, allowed_platforms, max_submissions_per_user) VALUES (?, ?, ?, ?, ?)",
            (contest_id, public_channel.id, review_channel.id, platform_str, submission_limit)
        )
        conn.commit()

        response_msg = (
            f"✅ Contest `{contest_id}` has been created!\n"
            f"📢 Public submissions will go to: {public_channel.mention}\n"
            f"🔒 Admin reviews will be in: {review_channel.mention}\n"
            f"👤 Submissions per user: **{submission_limit}**"
        )
        if platform_str:
            response_msg += f"\nPlatforms allowed: `{platform_str}`"

        await ctx.respond(response_msg, ephemeral=True)
    except sqlite3.IntegrityError:
        await ctx.respond(f"❌ A contest with the ID `{contest_id}` already exists.", ephemeral=True)
    finally:
        conn.close()


@contest.command(name="edit", description="Edit an existing contest's channels")
@commands.has_permissions(administrator=True)
async def edit_contest(
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "The ID of the contest to edit"),
    public_channel: Option(discord.TextChannel, "The new public channel for voting", required=False),
    review_channel: Option(discord.TextChannel, "The new private channel for admin review", required=False)
):
    if not public_channel and not review_channel:
        await ctx.respond("❌ You must provide at least one channel to edit.", ephemeral=True)
        return

    conn = get_db_connection()
    updates = []
    params = []
    if public_channel:
        updates.append("public_channel_id = ?")
        params.append(public_channel.id)
    if review_channel:
        updates.append("review_channel_id = ?")
        params.append(review_channel.id)

    params.append(contest_id)
    query = f"UPDATE contests SET {', '.join(updates)} WHERE contest_id = ?"

    cursor = conn.cursor()
    cursor.execute(query, tuple(params))

    if cursor.rowcount == 0:
        await ctx.respond(f"❌ Contest `{contest_id}` not found.", ephemeral=True)
    else:
        conn.commit()
        await ctx.respond(f"✅ Contest `{contest_id}` has been updated.", ephemeral=True)
    conn.close()


@contest.command(name="delete", description="Delete a contest and all its submissions")
@commands.has_permissions(administrator=True)
async def delete_contest(ctx: discord.ApplicationContext, contest_id: Option(str, "The ID of the contest to delete")):
    view = ConfirmationView(ctx.author.id)
    await ctx.respond(
        f"**⚠️ Are you sure you want to delete the contest `{contest_id}`?**\n"
        f"This will also delete ALL submissions associated with it. This action cannot be undone.",
        view=view,
        ephemeral=True
    )

    await view.wait() # Wait for the user to click a button

    if view.value is True:
        conn = get_db_connection()
        conn.execute("DELETE FROM submissions WHERE contest_id = ?", (contest_id,))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contests WHERE contest_id = ?", (contest_id,))

        if cursor.rowcount == 0:
            await ctx.edit(content=f"❌ Contest `{contest_id}` not found.", view=None)
        else:
            conn.commit()
            await ctx.edit(content=f"✅ Contest `{contest_id}` and all its submissions have been deleted.", view=None)
        conn.close()
    else:
        await ctx.edit(content="❌ Deletion cancelled.", view=None)


# --- SUBMISSION COMMANDS ---

@bot.command(name="submit", description="Submit your track from any supported platform to a contest")
async def submit(
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "The ID of the contest you're entering"),
    song_name: Option(str, "The name of your song"),
    url: Option(str, "The URL of your song from a supported platform")
):
    await ctx.defer(ephemeral=True)

    conn = get_db_connection()
    contest_data = conn.execute("SELECT * FROM contests WHERE contest_id = ?", (contest_id,)).fetchone()

    if not contest_data:
        await ctx.respond(f"❌ Contest `{contest_id}` not found. Please check the ID.", ephemeral=True)
        conn.close()
        return

    # Check submission limit
    limit = contest_data['max_submissions_per_user']
    user_submission_count = conn.execute(
        "SELECT COUNT(*) FROM submissions WHERE contest_id = ? AND user_id = ?",
        (contest_id, ctx.author.id)
    ).fetchone()[0]

    if user_submission_count >= limit:
        await ctx.respond(f"❌ You have already submitted the maximum of **{limit}** track(s) for this contest.", ephemeral=True)
        conn.close()
        return

    # Validate platform
    handler = get_platform_handler(url)
    if not handler:
        await ctx.respond("❌ This URL is not from a supported platform.", ephemeral=True)
        conn.close()
        return

    if contest_data['allowed_platforms']:
        allowed = contest_data['allowed_platforms'].split(',')
        if handler.name.lower() not in allowed:
            await ctx.respond(f"❌ This contest only allows submissions from: `{', '.join(allowed)}`.", ephemeral=True)
            conn.close()
            return

    metadata = handler.get_metadata(url)
    if not metadata:
        await ctx.respond("❌ Could not retrieve song data from the URL. Please check the link.", ephemeral=True)
        conn.close()
        return

    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO submissions (contest_id, user_id, user_name, song_name, platform, suno_url) VALUES (?, ?, ?, ?, ?, ?)",
            (contest_id, ctx.author.id, str(ctx.author), song_name, handler.name, metadata['embed_url'])
        )
        submission_id = cursor.lastrowid
        conn.commit()

        public_channel = bot.get_channel(contest_data['public_channel_id'])
        review_channel = bot.get_channel(contest_data['review_channel_id'])

        review_embed = discord.Embed(title=f"New Submission: {song_name}", color=discord.Color.orange())
        review_embed.add_field(name="Submitter", value=ctx.author.mention, inline=False)
        review_embed.add_field(name="Platform", value=handler.name, inline=False)
        review_embed.add_field(name="URL", value=metadata['embed_url'], inline=False)
        review_embed.set_footer(text=f"Submission ID: {submission_id}")
        review_message = await review_channel.send(embed=review_embed)

        public_embed = discord.Embed(
            title=song_name,
            description=f"by **{metadata['author']}** on **{handler.name}**\n[Listen Here]({metadata['embed_url']})",
            color=discord.Color.blue()
        )
        if metadata.get('image_url'):
            public_embed.set_image(url=metadata['image_url'])
        public_embed.set_footer(text=f"Submission ID: {submission_id} | Contest: {contest_id}")
        public_message = await public_channel.send(content=metadata['embed_url'], embed=public_embed)
        await public_message.add_reaction("✅")

        conn.execute(
            "UPDATE submissions SET public_message_id = ?, review_message_id = ? WHERE submission_id = ?",
            (public_message.id, review_message.id, submission_id)
        )
        conn.commit()

        await ctx.respond(f"✅ Your submission (`ID: {submission_id}`) from **{handler.name}** was successful!", ephemeral=True)
    except Exception as e:
        print(f"An error occurred during submission: {e}")
        await ctx.respond("An error occurred. Please contact an admin.", ephemeral=True)
    finally:
        conn.close()


@submission_group.command(name="delete", description="Delete one of your submissions.")
async def delete_submission(ctx: discord.ApplicationContext, submission_id: Option(int, "The ID of the submission to delete")):
    conn = get_db_connection()
    submission = conn.execute("SELECT * FROM submissions WHERE submission_id = ?", (submission_id,)).fetchone()

    if not submission:
        await ctx.respond(f"❌ Submission with ID `{submission_id}` not found.", ephemeral=True)
        conn.close()
        return

    is_admin = ctx.author.guild_permissions.administrator
    if submission['user_id'] != ctx.author.id and not is_admin:
        await ctx.respond("❌ You can only delete your own submissions.", ephemeral=True)
        conn.close()
        return

    view = ConfirmationView(ctx.author.id)
    await ctx.respond(f"**⚠️ Are you sure you want to delete submission `{submission_id}`?**\nThis cannot be undone.", view=view, ephemeral=True)

    await view.wait()

    if view.value is True:
        try:
            contest_data = conn.execute("SELECT * FROM contests WHERE contest_id = ?", (submission['contest_id'],)).fetchone()
            if contest_data:
                public_channel = bot.get_channel(contest_data['public_channel_id'])
                review_channel = bot.get_channel(contest_data['review_channel_id'])

                if public_channel and submission['public_message_id']:
                    try:
                        msg = await public_channel.fetch_message(submission['public_message_id'])
                        await msg.delete()
                    except discord.NotFound: pass
                if review_channel and submission['review_message_id']:
                    try:
                        msg = await review_channel.fetch_message(submission['review_message_id'])
                        await msg.delete()
                    except discord.NotFound: pass

            conn.execute("DELETE FROM submissions WHERE submission_id = ?", (submission_id,))
            conn.commit()
            await ctx.edit(content=f"✅ Submission `{submission_id}` has been deleted.", view=None)
        except Exception as e:
            print(f"Error deleting submission: {e}")
            await ctx.edit(content="An error occurred while deleting the submission messages.", view=None)
    else:
        await ctx.edit(content="❌ Deletion cancelled.", view=None)

    conn.close()


# --- REGISTER COMMANDS AND RUN BOT ---
bot.add_application_command(contest)
bot.add_application_command(submission_group)

bot.run(TOKEN)
