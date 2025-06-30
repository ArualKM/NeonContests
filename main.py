# main.py
import discord
from discord.commands import SlashCommandGroup, Option
from discord.ext import commands
import os
import sqlite3
from dotenv import load_dotenv
from platforms import get_platform_handler, platform_handlers # Import our new platform tools

# --- BOT SETUP (Same as before) ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = discord.Bot(intents=intents)

# --- HELPER FUNCTIONS & VIEWS (Same as before) ---
def get_db_connection():
    conn = sqlite3.connect('suno_contests.db')
    conn.row_factory = sqlite3.Row
    return conn

class ConfirmationView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30.0)
        self.value = None
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        self.stop()

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

# --- COMMANDS (Updated) ---
contest = SlashCommandGroup("contest", "Commands for managing music contests")
submission_group = SlashCommandGroup("submission", "Commands for managing your submissions")

@contest.command(name="create", description="Create a new music contest")
@commands.has_permissions(administrator=True)
async def create_contest(
    ctx,
    contest_id: str,
    public_channel: discord.TextChannel,
    review_channel: discord.TextChannel,
    allowed_platforms: Option(str, "Comma-separated list of allowed platforms (e.g., 'suno,youtube')", required=False, default=None)
):
    """Admin command to create a contest, now with platform restrictions."""
    conn = get_db_connection()
    try:
        # Validate platform names
        if allowed_platforms:
            valid_platforms = [p.name.lower() for p in platform_handlers]
            platforms_list = [p.strip().lower() for p in allowed_platforms.split(',')]
            if not all(p in valid_platforms for p in platforms_list):
                await ctx.respond(f"❌ Invalid platform name. Valid options are: {', '.join(valid_platforms)}", ephemeral=True)
                return
            platform_str = ",".join(platforms_list)
        else:
            platform_str = None

        conn.execute("INSERT INTO contests (contest_id, public_channel_id, review_channel_id, allowed_platforms) VALUES (?, ?, ?, ?)",
                     (contest_id, public_channel.id, review_channel.id, platform_str))
        conn.commit()
        response_msg = f"✅ Contest `{contest_id}` created!"
        if platform_str:
            response_msg += f"\nAllowed Platforms: `{platform_str}`"
        await ctx.respond(response_msg, ephemeral=True)
    except sqlite3.IntegrityError:
        await ctx.respond(f"❌ A contest with the ID `{contest_id}` already exists.", ephemeral=True)
    finally:
        conn.close()

@bot.command(name="submit", description="Submit your track from any supported platform to a contest")
async def submit(ctx, contest_id: str, song_name: str, url: str):
    await ctx.defer(ephemeral=True)
    
    conn = get_db_connection()
    contest_data = conn.execute("SELECT * FROM contests WHERE contest_id = ?", (contest_id,)).fetchone()

    if not contest_data:
        await ctx.respond(f"❌ Contest `{contest_id}` not found.", ephemeral=True)
        conn.close()
        return

    # --- Platform Validation Logic ---
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
            
    # --- Metadata Fetching ---
    metadata = handler.get_metadata(url)
    if not metadata:
        await ctx.respond("❌ Could not retrieve song data from the URL. Please check the link.", ephemeral=True)
        conn.close()
        return

    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO submissions (contest_id, user_id, user_name, song_name, platform, suno_url) VALUES (?, ?, ?, ?, ?, ?)",
                       (contest_id, ctx.author.id, str(ctx.author), song_name, handler.name, metadata['embed_url']))
        submission_id = cursor.lastrowid
        conn.commit()

        public_channel = bot.get_channel(contest_data['public_channel_id'])
        review_channel = bot.get_channel(contest_data['review_channel_id'])

        # --- Post to Review Channel ---
        review_embed = discord.Embed(title=f"New Submission: {song_name}", color=discord.Color.orange())
        review_embed.add_field(name="Submitter", value=ctx.author.mention, inline=False)
        review_embed.add_field(name="Platform", value=handler.name, inline=False)
        review_embed.add_field(name="URL", value=metadata['embed_url'], inline=False)
        review_embed.set_footer(text=f"Submission ID: {submission_id}")
        review_message = await review_channel.send(embed=review_embed)

        # --- Post to Public Channel ---
        public_embed = discord.Embed(
            title=song_name,
            description=f"by **{metadata['author']}** on **{handler.name}**\n[Listen Here]({metadata['embed_url']})",
            color=discord.Color.blue()
        )
        if metadata['image_url']:
            public_embed.set_image(url=metadata['image_url'])
        public_embed.set_footer(text=f"Submission ID: {submission_id} | Contest: {contest_id}")
        
        # Send the embed and URL content (for Discord's auto-player)
        public_message = await public_channel.send(content=metadata['embed_url'], embed=public_embed)
        await public_message.add_reaction("✅")

        conn.execute("UPDATE submissions SET public_message_id = ?, review_message_id = ? WHERE submission_id = ?",
                     (public_message.id, review_message.id, submission_id))
        conn.commit()

        await ctx.respond(f"✅ Your submission (`ID: {submission_id}`) from **{handler.name}** was successful!", ephemeral=True)
    except Exception as e:
        print(f"An error occurred during submission: {e}")
        await ctx.respond("An error occurred. Please contact an admin.", ephemeral=True)
    finally:
        conn.close()

# Add other commands (edit/delete contest, delete submission) here
# They do not need significant changes as they rely on IDs already in the DB.
# Make sure to re-add them from the previous version.

bot.add_application_command(contest)
bot.add_application_command(submission_group)
bot.run(TOKEN)
