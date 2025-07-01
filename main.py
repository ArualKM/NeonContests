# main.py - Complete production-ready Discord bot
import discord
from discord.commands import SlashCommandGroup, Option
from discord.ext import commands, tasks
import os
import sqlite3
import re
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import urlparse
from dotenv import load_dotenv

# Import our modules
from config import Config
from database import get_db, init_db, migrate_db, verify_integrity, log_action, get_contest_stats
from platforms import PlatformManager
from utils import RateLimiter, validate_contest_id, validate_song_name, validate_url

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('music_contest_bot')

# --- BOT SETUP ---
load_dotenv()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Bot(intents=intents)

# Initialize rate limiters
submit_limiter = RateLimiter(max_calls=5, time_window=60)
delete_limiter = RateLimiter(max_calls=10, time_window=60)

# Platform manager instance
platform_manager = PlatformManager()

# --- UI VIEWS ---
class ConfirmationView(discord.ui.View):
    """A view with Confirm and Cancel buttons for deletion actions."""
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
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        self.stop()
        await interaction.response.defer()

# --- PERMISSION CHECKS ---
def is_contest_manager():
    """Check if user has contest management permissions"""
    async def predicate(ctx):
        manager_role = discord.utils.get(ctx.guild.roles, name="Contest Manager")
        return (manager_role and manager_role in ctx.author.roles) or \
               ctx.author.guild_permissions.administrator
    return commands.check(predicate)

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    """Event that runs when the bot is connected and ready."""
    logger.info(f'{bot.user} has connected to Discord!')
    
    # Initialize database
    try:
        init_db()
        migrate_db()
        if verify_integrity():
            logger.info("Database initialized and verified successfully")
        else:
            logger.error("Database integrity check failed!")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
    
    # Start background tasks
    cleanup_old_data.start()
    logger.info('Bot is ready and listening for commands.')

@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error: discord.DiscordException):
    """Global error handler for application commands."""
    if isinstance(error, commands.CheckFailure):
        await ctx.respond("❌ You don't have permission to use this command.", ephemeral=True)
    else:
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=True)
        await ctx.respond("❌ An unexpected error occurred. Please try again later.", ephemeral=True)

# --- BACKGROUND TASKS ---
@tasks.loop(hours=24)
async def cleanup_old_data():
    """Clean up old rate limit data and create backups"""
    try:
        from database import create_backup
        create_backup()
        logger.info("Daily backup completed")
    except Exception as e:
        logger.error(f"Backup task error: {e}")

# --- COMMAND GROUPS ---
contest = SlashCommandGroup("contest", "Commands for managing music contests")
submission_group = SlashCommandGroup("submission", "Commands for managing your submissions")

# --- CONTEST MANAGEMENT COMMANDS ---
@contest.command(name="create", description="Create a new music contest")
@is_contest_manager()
async def create_contest(
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "A unique ID for the contest (e.g., 'summer2025')"),
    public_channel: Option(discord.TextChannel, "The public channel for voting"),
    review_channel: Option(discord.TextChannel, "The private channel for admin review"),
    allowed_platforms: Option(str, "Comma-separated list (e.g., 'suno,youtube')", required=False, default=None),
    submission_limit: Option(int, "Max submissions per user (1-10)", min_value=1, max_value=10, required=False, default=1),
    description: Option(str, "Contest description", required=False, default=None)
):

    await ctx.defer(ephemeral=True)

    """Create a new contest with validation"""
    
    # Validate inputs
    if not validate_contest_id(contest_id):
        await ctx.respond(
            "❌ Invalid contest ID. Use 3-30 characters (letters, numbers, hyphens only).",
            ephemeral=True
        )
        return
    
    # Validate platforms
    platform_str = None
    if allowed_platforms:
        valid_platforms = [h.name.lower() for h in platform_manager.handlers]
        platforms_list = [p.strip().lower() for p in allowed_platforms.split(',')]
        
        invalid_platforms = [p for p in platforms_list if p not in valid_platforms]
        if invalid_platforms:
            await ctx.respond(
                f"❌ Invalid platforms: {', '.join(invalid_platforms)}\n"
                f"Valid options: {', '.join(valid_platforms)}",
                ephemeral=True
            )
            return
        platform_str = ",".join(platforms_list)
    
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO contests 
                   (contest_id, public_channel_id, review_channel_id, 
                    allowed_platforms, max_submissions_per_user, created_by, description) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (contest_id, public_channel.id, review_channel.id, 
                 platform_str, submission_limit, ctx.author.id, description)
            )
            
            log_action(ctx.author.id, "create_contest", f"Created contest: {contest_id}")
            logger.info(f"Contest {contest_id} created by {ctx.author}")
            
            embed = discord.Embed(
                title="✅ Contest Created Successfully!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Contest ID", value=f"`{contest_id}`", inline=True)
            embed.add_field(name="Max Submissions", value=str(submission_limit), inline=True)
            embed.add_field(name="Status", value="Active", inline=True)
            embed.add_field(name="Public Channel", value=public_channel.mention, inline=True)
            embed.add_field(name="Review Channel", value=review_channel.mention, inline=True)
            
            if platform_str:
                embed.add_field(name="Allowed Platforms", value=f"`{platform_str}`", inline=True)
            if description:
                embed.add_field(name="Description", value=description[:1024], inline=False)
            
            embed.set_footer(text=f"Created by {ctx.author}")
            
            await ctx.followup.send(embed=embed, ephemeral=True)
            
    except sqlite3.IntegrityError:
        await ctx.respond(
            f"❌ Contest ID `{contest_id}` already exists.",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error creating contest: {e}", exc_info=True)
        await ctx.respond(
            "❌ An error occurred while creating the contest.",
            ephemeral=True
        )

@contest.command(name="edit", description="Edit an existing contest")
@is_contest_manager()
async def edit_contest(
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "The ID of the contest to edit"),
    public_channel: Option(discord.TextChannel, "The new public channel", required=False),
    review_channel: Option(discord.TextChannel, "The new review channel", required=False),
    submission_limit: Option(int, "New submission limit", min_value=1, max_value=10, required=False),
    status: Option(str, "Contest status", choices=["active", "voting", "closed"], required=False)
):
    """Edit contest settings"""
    
    if not any([public_channel, review_channel, submission_limit, status]):
        await ctx.respond("❌ You must provide at least one field to edit.", ephemeral=True)
        return
    
    try:
        with get_db() as conn:
            # Build update query
            updates = []
            params = []
            
            if public_channel:
                updates.append("public_channel_id = ?")
                params.append(public_channel.id)
            if review_channel:
                updates.append("review_channel_id = ?")
                params.append(review_channel.id)
            if submission_limit:
                updates.append("max_submissions_per_user = ?")
                params.append(submission_limit)
            if status:
                updates.append("status = ?")
                params.append(status)
            
            params.append(contest_id)
            query = f"UPDATE contests SET {', '.join(updates)} WHERE contest_id = ?"
            
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if cursor.rowcount == 0:
                await ctx.respond(f"❌ Contest `{contest_id}` not found.", ephemeral=True)
                return
            
            log_action(ctx.author.id, "edit_contest", f"Edited contest: {contest_id}")            

            # Fetch updated contest data
            updated_contest = conn.execute(
                "SELECT * FROM contests WHERE contest_id = ?",
                (contest_id,)
            ).fetchone()
            
            embed = discord.Embed(
                title="✅ Contest Updated",
                description=f"Contest `{contest_id}` has been updated successfully.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            # Display updated values
            if updated_contest:
                if public_channel:
                    embed.add_field(name="Public Channel", value=f"<#{updated_contest['public_channel_id']}>", inline=True)
                if review_channel:
                    embed.add_field(name="Review Channel", value=f"<#{updated_contest['review_channel_id']}>", inline=True)
                if submission_limit:
                    embed.add_field(name="Submission Limit", value=updated_contest['max_submissions_per_user'], inline=True)
                if status:
                    embed.add_field(name="Status", value=updated_contest['status'], inline=True)
                if description:
                    embed.add_field(name="Description", value=updated_contest['description'], inline=False)

            await ctx.followup.send(embed=embed, ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error editing contest: {e}", exc_info=True)
        await ctx.respond("❌ An error occurred while editing the contest.", ephemeral=True)

@contest.command(name="delete", description="Delete a contest and all its submissions")
@is_contest_manager()
async def delete_contest(
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "The ID of the contest to delete")
):
    """Delete a contest with confirmation"""
    
    # Get contest info first
    try:
        with get_db() as conn:
            contest_info = conn.execute(
                "SELECT * FROM contests WHERE contest_id = ?",
                (contest_id,)
            ).fetchone()
            
            if not contest_info:
                await ctx.respond(f"❌ Contest `{contest_id}` not found.", ephemeral=True)
                return
            
            submission_count = conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE contest_id = ?",
                (contest_id,)
            ).fetchone()[0]
        
        view = ConfirmationView(ctx.author.id)
        
        embed = discord.Embed(
            title="⚠️ Confirm Contest Deletion",
            description=f"Are you sure you want to delete contest `{contest_id}`?",
            color=discord.Color.orange()
        )
        embed.add_field(name="Submissions", value=str(submission_count), inline=True)
        embed.add_field(name="Status", value=contest_info['status'], inline=True)
        embed.add_field(
            name="Warning",
            value="This will permanently delete the contest and ALL submissions!",
            inline=False
        )
        
        await ctx.respond(embed=embed, view=view, ephemeral=True)
        await view.wait()
        
        if view.value is True:
            with get_db() as conn:
                # Delete all submissions first (for logging)
                conn.execute("DELETE FROM submissions WHERE contest_id = ?", (contest_id,))
                conn.execute("DELETE FROM contests WHERE contest_id = ?", (contest_id,))
                
                log_action(ctx.author.id, "delete_contest", 
                          f"Deleted contest: {contest_id} ({submission_count} submissions)")
            
            await ctx.edit(
                content=f"✅ Contest `{contest_id}` and {submission_count} submissions deleted.",
                embed=None,
                view=None
            )
        else:
            await ctx.edit(content="❌ Deletion cancelled.", embed=None, view=None)
            
    except Exception as e:
        logger.error(f"Error deleting contest: {e}", exc_info=True)
        await ctx.respond("❌ An error occurred while deleting the contest.", ephemeral=True)

@contest.command(name="stats", description="View contest statistics")
async def _contest_stats(  # Rename the function
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "The ID of the contest")
):
    """Display detailed contest statistics"""
    
    try:
        stats = get_contest_stats(contest_id)
        
        if not stats:
            await ctx.respond(f"❌ Contest `{contest_id}` not found.", ephemeral=True)
            return

        ...

@bot.command(name="contest_stats", description="View contest statistics")  # Register as a top-level command
@is_contest_manager()  # Apply the permission check
async def contest_stats(
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "The ID of the contest")
):
    await _contest_stats(ctx, contest_id) # Call the original function
        
        contest_info = stats['contest']
        
        embed = discord.Embed(
            title=f"📊 Contest Statistics: {contest_id}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Status", value=contest_info['status'].title(), inline=True)
        embed.add_field(name="Total Submissions", value=stats['total_submissions'], inline=True)
        embed.add_field(name="Unique Participants", value=stats['unique_participants'], inline=True)
        
        # Platform breakdown
        if stats['platforms']:
            platform_text = "\n".join([f"**{p}**: {c}" for p, c in stats['platforms'].items()])
            embed.add_field(name="Submissions by Platform", value=platform_text, inline=False)
        
        # Top submissions if voting is enabled
        if 'votes' in stats and stats['votes']:
            top_5 = stats['votes'][:5]
            leaderboard = []
            for i, sub in enumerate(top_5, 1):
                leaderboard.append(
                    f"{i}. **{sub['song_name']}** by {sub['user_name']} "
                    f"({sub['vote_count']} votes)"
                )
            embed.add_field(
                name="🏆 Current Leaders",
                value="\n".join(leaderboard) or "No votes yet",
                inline=False
            )
        
        try:
            await ctx.respond(embed=embed, ephemeral=False)
        
        except Exception as e:
            logger.error(f"Error getting contest stats: {e}", exc_info=True)
            await ctx.respond("❌ An error occurred while fetching statistics.", ephemeral=True)

# --- SUBMISSION COMMANDS ---
@bot.command(name="submit", description="Submit your track to a contest")
async def submit(
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "The ID of the contest you're entering"),
    song_name: Option(str, "The name of your song (max 100 characters)"),
    url: Option(str, "The URL of your song from a supported platform")
):
    """Submit a track with full validation and error handling"""
    
    # Defer to show bot is processing
    await ctx.defer(ephemeral=True)
    
    # Rate limiting
    if not submit_limiter.is_allowed(ctx.author.id):
        await ctx.followup.send(
            "❌ You're submitting too quickly. Please wait a moment and try again.",
            ephemeral=True
        )
        return
    
    # Input validation
    if not validate_contest_id(contest_id):
        await ctx.followup.send(
            "❌ Invalid contest ID format. Use only letters, numbers, and hyphens.",
            ephemeral=True
        )
        return
    
    if not validate_song_name(song_name):
        await ctx.followup.send(
            f"❌ Invalid song name. Maximum {Config.MAX_SONG_NAME_LENGTH} characters, no special characters.",
            ephemeral=True
        )
        return
    
    if not validate_url(url):
        await ctx.followup.send(
            "❌ Invalid URL format. Please provide a valid HTTP(S) URL.",
            ephemeral=True
        )
        return
    
    try:
        with get_db() as conn:
            # Get contest data
            contest_data = conn.execute(
                "SELECT * FROM contests WHERE contest_id = ? AND status IN ('active', 'voting')",
                (contest_id,)
            ).fetchone()
            
            if not contest_data:
                await ctx.followup.send(
                    f"❌ Contest `{contest_id}` not found or is closed for submissions.",
                    ephemeral=True
                )
                return
            
            # Begin transaction for atomic operations
            cursor = conn.cursor()
            cursor.execute("BEGIN EXCLUSIVE")
            
            try:
                # Check submission limit
                user_submission_count = cursor.execute(
                    "SELECT COUNT(*) FROM submissions WHERE contest_id = ? AND user_id = ?",
                    (contest_id, ctx.author.id)
                ).fetchone()[0]
                
                limit = contest_data['max_submissions_per_user']
                if user_submission_count >= limit:
                    cursor.execute("ROLLBACK")
                    await ctx.followup.send(
                        f"❌ You have already submitted the maximum of **{limit}** track(s) for this contest.",
                        ephemeral=True
                    )
                    return
                
                # Get platform handler
                handler = await platform_manager.get_platform_handler(url)
                if not handler:
                    cursor.execute("ROLLBACK")
                    await ctx.followup.send(
                        "❌ This URL is not from a supported platform. "
                        f"Supported: {', '.join([h.name for h in platform_manager.handlers])}",
                        ephemeral=True
                    )
                    return
                
                # Check allowed platforms
                if contest_data['allowed_platforms']:
                    allowed = contest_data['allowed_platforms'].split(',')
                    if handler.name.lower() not in allowed:
                        cursor.execute("ROLLBACK")
                        await ctx.followup.send(
                            f"❌ This contest only allows submissions from: `{', '.join(allowed)}`.",
                            ephemeral=True
                        )
                        return
                
                # Fetch metadata
                metadata = await handler.get_metadata(url)
                if not metadata:
                    cursor.execute("ROLLBACK")
                    await ctx.followup.send(
                        "❌ Could not retrieve song data from the URL. Please check the link.",
                        ephemeral=True
                    )
                    return
                
                # Insert submission
                cursor.execute(
                    """INSERT INTO submissions 
                       (contest_id, user_id, user_name, song_name, platform, suno_url, metadata) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (contest_id, ctx.author.id, str(ctx.author), song_name, 
                     handler.name, metadata['embed_url'], None)
                )
                submission_id = cursor.lastrowid
                
                # Get channels
                public_channel = bot.get_channel(contest_data['public_channel_id'])
                review_channel = bot.get_channel(contest_data['review_channel_id'])
                
                if not public_channel or not review_channel:
                    cursor.execute("ROLLBACK")
                    logger.error(f"Missing channels for contest {contest_id}")
                    await ctx.followup.send(
                        "⚠️ Contest channels not properly configured. Please contact an admin.",
                        ephemeral=True
                    )
                    return
                
                # Create and send messages
                try:
                    # Review channel embed
                    review_embed = discord.Embed(
                        title=f"New Submission: {song_name}",
                        color=discord.Color.orange(),
                        timestamp=datetime.now()
                    )
                    review_embed.add_field(name="Submitter", value=ctx.author.mention, inline=True)
                    review_embed.add_field(name="User ID", value=str(ctx.author.id), inline=True)
                    review_embed.add_field(name="Platform", value=handler.name, inline=True)
                    review_embed.add_field(name="URL", value=metadata['embed_url'], inline=False)
                    review_embed.set_footer(text=f"Submission ID: {submission_id}")
                    
                    review_message = await review_channel.send(embed=review_embed)
                    
                    # Public channel embed
                    public_embed = discord.Embed(
                        title=song_name,
                        description=f"by **{metadata.get('author', 'Unknown Artist')}** on **{handler.name}**\n[Listen Here]({metadata['embed_url']})",
                        color=discord.Color.blue(),
                        timestamp=datetime.now()
                    )
                    
                    if metadata.get('image_url'):
                        public_embed.set_image(url=metadata['image_url'])
                    
                    public_embed.set_footer(
                        text=f"Submission ID: {submission_id} | Contest: {contest_id}"
                    )
                    
                    public_message = await public_channel.send(
                        content=metadata['embed_url'],
                        embed=public_embed
                    )
                    
                    # Add voting reaction
                    await public_message.add_reaction("✅")
                    
                    # Update database with message IDs
                    cursor.execute(
                        """UPDATE submissions 
                           SET public_message_id = ?, review_message_id = ? 
                           WHERE submission_id = ?""",
                        (public_message.id, review_message.id, submission_id)
                    )
                    
                    cursor.execute("COMMIT")
                    
                    # Log successful submission
                    log_action(ctx.author.id, "submit", f"Submitted to contest {contest_id}")
                    logger.info(
                        f"Submission {submission_id} created by {ctx.author} "
                        f"for contest {contest_id}"
                    )
                    
                    # Success response
                    success_embed = discord.Embed(
                        title="✅ Submission Successful!",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    success_embed.add_field(name="Submission ID", value=f"`{submission_id}`", inline=True)
                    success_embed.add_field(name="Song", value=song_name, inline=True)
                    success_embed.add_field(name="Platform", value=handler.name, inline=True)
                    success_embed.add_field(name="Contest", value=f"`{contest_id}`", inline=True)
                    success_embed.add_field(
                        name="View Submission",
                        value=f"Check {public_channel.mention} to see your submission",
                        inline=False
                    )
                    
                    await ctx.followup.send(embed=success_embed, ephemeral=True)
                    
                except discord.Forbidden:
                    cursor.execute("ROLLBACK")
                    logger.error(f"Missing permissions to post in channels for contest {contest_id}")
                    await ctx.followup.send(
                        "❌ Bot lacks permissions to post in contest channels. Please contact an admin.",
                        ephemeral=True
                    )
                    
                except discord.HTTPException as e:
                    cursor.execute("ROLLBACK")
                    logger.error(f"Discord API error during submission: {e}")
                    await ctx.followup.send(
                        "❌ Discord error occurred. Please try again later.",
                        ephemeral=True
                    )
                    
            except Exception as e:
                cursor.execute("ROLLBACK")
                logger.error(f"Database error during submission: {e}", exc_info=True)
                await ctx.followup.send(
                    "❌ A database error occurred. Please try again or contact an admin.",
                    ephemeral=True
                )
                
    except Exception as e:
        if not ctx.responded:  # Ensure a response if the initial deferral failed
            await ctx.respond(
                "❌ An unexpected error occurred. Please try again or contact an admin.",
                ephemeral=True
            )
            logger.error(f"Error in submit command: {e}", exc_info=True)
@submission_group.command(name="delete", description="Delete one of your submissions")
async def delete_submission(
    ctx: discord.ApplicationContext,
    submission_id: Option(int, "The ID of the submission to delete", min_value=1)
):
    """Delete a submission with proper cleanup"""
    
    # Rate limiting
    if not delete_limiter.is_allowed(ctx.author.id):
        await ctx.respond(
            "❌ Too many deletion requests. Please wait a moment.",
            ephemeral=True
        )
        return
    
    try:
        with get_db() as conn:
            # Get submission details
            submission = conn.execute(
                """SELECT s.*, c.public_channel_id, c.review_channel_id 
                   FROM submissions s
                   JOIN contests c ON s.contest_id = c.contest_id
                   WHERE s.submission_id = ?""",
                (submission_id,)
            ).fetchone()
            
            if not submission:
                await ctx.respond(
                    f"❌ Submission with ID `{submission_id}` not found.",
                    ephemeral=True
                )
                return
            
            # Check permissions
            is_admin = ctx.author.guild_permissions.administrator
            is_manager = await is_contest_manager().predicate(ctx)
            is_owner = submission['user_id'] == ctx.author.id
            
            if not (is_owner or is_admin or is_manager):
                await ctx.respond(
                    "❌ You can only delete your own submissions.",
                    ephemeral=True
                )
                return
            
            # Create confirmation view
            view = ConfirmationView(ctx.author.id)
            
            # Build confirmation embed
            confirm_embed = discord.Embed(
                title="⚠️ Confirm Deletion",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            confirm_embed.add_field(name="Submission ID", value=f"`{submission_id}`", inline=True)
            confirm_embed.add_field(name="Song", value=submission['song_name'], inline=True)
            confirm_embed.add_field(name="Contest", value=f"`{submission['contest_id']}`", inline=True)
            
            if (is_admin or is_manager) and not is_owner:
                confirm_embed.add_field(
                    name="Submitted by",
                    value=submission['user_name'],
                    inline=False
                )
            
            confirm_embed.set_footer(text="This action cannot be undone")
            
            await ctx.respond(embed=confirm_embed, view=view, ephemeral=True)
            await view.wait()
            
            if view.value is True:
                # Delete Discord messages
                deletion_errors = []
                
                public_channel = bot.get_channel(submission['public_channel_id'])
                review_channel = bot.get_channel(submission['review_channel_id'])
                
                # Delete public message
                if public_channel and submission['public_message_id']:
                    try:
                        msg = await public_channel.fetch_message(submission['public_message_id'])
                        await msg.delete()
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        deletion_errors.append("Missing permissions for public channel")
                    except Exception as e:
                        logger.error(f"Error deleting public message: {e}")
                        deletion_errors.append("Failed to delete public message")
                
                # Delete review message
                if review_channel and submission['review_message_id']:
                    try:
                        msg = await review_channel.fetch_message(submission['review_message_id'])
                        await msg.delete()
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        deletion_errors.append("Missing permissions for review channel")
                    except Exception as e:
                        logger.error(f"Error deleting review message: {e}")
                        deletion_errors.append("Failed to delete review message")
                
                # Delete from database
                conn.execute(
                    "DELETE FROM submissions WHERE submission_id = ?",
                    (submission_id,)
                )
                
                # Log the action
                log_action(
                    ctx.author.id,
                    "delete_submission",
                    f"Deleted submission {submission_id} (owner: {is_owner})"
                )
                
                # Build response
                if deletion_errors:
                    response = (
                        f"⚠️ Submission `{submission_id}` deleted from database.\n"
                        f"**Warnings:**\n" + "\n".join(f"• {e}" for e in deletion_errors)
                    )
                else:
                    response = f"✅ Submission `{submission_id}` has been completely deleted."
                
                await ctx.edit(content=response, embed=None, view=None)
                
            else:
                await ctx.edit(content="❌ Deletion cancelled.", embed=None, view=None)
                
    except Exception as e:
        logger.error(f"Error in delete_submission: {e}", exc_info=True)
        await ctx.respond(
            "❌ An error occurred while deleting the submission.",
            ephemeral=True
        )

@submission_group.command(name="list", description="List your submissions")
async def list_submissions(
    ctx: discord.ApplicationContext,
    contest_id: Option(str, "Filter by contest ID", required=False, default=None)
):
    """List user's submissions"""
    
    try:
        with get_db() as conn:
            if contest_id:
                if not validate_contest_id(contest_id):
                    await ctx.respond(
                        "❌ Invalid contest ID format.",
                        ephemeral=True
                    )
                    return
                
                submissions = conn.execute(
                    """SELECT s.*, c.status as contest_status
                       FROM submissions s
                       JOIN contests c ON s.contest_id = c.contest_id
                       WHERE s.user_id = ? AND s.contest_id = ?
                       ORDER BY s.created_at DESC
                       LIMIT 25""",
                    (ctx.author.id, contest_id)
                ).fetchall()
            else:
                submissions = conn.execute(
                    """SELECT s.*, c.status as contest_status
                       FROM submissions s
                       JOIN contests c ON s.contest_id = c.contest_id
                       WHERE s.user_id = ?
                       ORDER BY s.created_at DESC
                       LIMIT 25""",
                    (ctx.author.id,)
                ).fetchall()
            
            if not submissions:
                msg = "You have no submissions"
                if contest_id:
                    msg += f" in contest `{contest_id}`"
                await ctx.respond(f"{msg}.", ephemeral=True)
                return
            
            # Create paginated embed
            embed = discord.Embed(
                title="Your Submissions",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            if contest_id:
                embed.description = f"Contest: `{contest_id}`"
            
            for i, sub in enumerate(submissions[:10]):
                field_value = (
                    f"**ID:** `{sub['submission_id']}`\n"
                    f"**Platform:** {sub['platform']}\n"
                    f"**Contest:** `{sub['contest_id']}` ({sub['contest_status']})\n"
                    f"**Submitted:** <t:{int(datetime.fromisoformat(sub['created_at']).timestamp())}:R>"
                )
                
                embed.add_field(
                    name=f"{i+1}. {sub['song_name'][:50]}",
                    value=field_value,
                    inline=False
                )
            
            if len(submissions) > 10:
                embed.set_footer(text=f"Showing 10 of {len(submissions)} submissions")
            else:
                embed.set_footer(text=f"Total: {len(submissions)} submission(s)")
            
            await ctx.respond(embed=embed, ephemeral=True)
            
    except Exception as e:
        logger.error(f"Error in list_submissions: {e}", exc_info=True)
        await ctx.respond(
            "❌ An error occurred while fetching your submissions.",
            ephemeral=True
        )

# --- UTILITY COMMANDS ---
@bot.command(name="help", description="Get help with the bot")
async def help_command(ctx: discord.ApplicationContext):
    """Display help information"""
    
    embed = discord.Embed(
        title="🎵 Music Contest Bot Help",
        description="Submit your music creations and participate in contests!",
        color=discord.Color.blue()
    )
    
    # User commands
    embed.add_field(
        name="📝 Submission Commands",
        value=(
            "`/submit` - Submit a track to a contest\n"
            "`/submission list` - View your submissions\n"
            "`/submission delete` - Delete one of your submissions"
        ),
        inline=False
    )
    
    # Contest info
    embed.add_field(
        name="🏆 Contest Commands",
        value=(
            "`/contest stats` - View contest statistics and leaderboard"
        ),
        inline=False
    )
    
    # Admin commands (only show if user has permissions)
    if ctx.author.guild_permissions.administrator:
        embed.add_field(
            name="⚙️ Admin Commands",
            value=(
                "`/contest create` - Create a new contest\n"
                "`/contest edit` - Edit contest settings\n"
                "`/contest delete` - Delete a contest"
            ),
            inline=False
        )
    
    # Supported platforms
    platforms = ", ".join([h.name for h in platform_manager.handlers])
    embed.add_field(
        name="🎵 Supported Platforms",
        value=platforms,
        inline=False
    )
    
    embed.set_footer(text="Need more help? Contact an administrator!")
    
    await ctx.respond(embed=embed, ephemeral=True)

# --- CLEANUP ---
@bot.event
async def on_disconnect():
    """Cleanup when bot disconnects"""
    await platform_manager.close_all()
    logger.info("Bot disconnected, cleaned up resources")

# --- REGISTER COMMANDS AND RUN ---
bot.add_application_command(contest)
bot.add_application_command(submission_group)

if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("DISCORD_TOKEN not found in environment variables!")
        exit(1)
    
    try:
        bot.run(token)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        exit(1)
