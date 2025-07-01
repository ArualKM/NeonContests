# utils.py - Utility functions and classes for the Discord bot
import re
import logging
import discord
import aiohttp
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List
from config import Config

logger = logging.getLogger('utils')

# --- Rate Limiter ---
class RateLimiter:
    """Rate limiter to prevent spam and abuse"""
    
    def __init__(self, max_calls: int, time_window: int):
        """
        Initialize rate limiter
        
        Args:
            max_calls: Maximum number of calls allowed
            time_window: Time window in seconds
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = defaultdict(list)
    
    def is_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to make a call"""
        now = datetime.now().timestamp()
        
        # Clean old calls
        self.calls[user_id] = [
            call_time for call_time in self.calls[user_id]
            if now - call_time < self.time_window
        ]
        
        # Check if under limit
        if len(self.calls[user_id]) < self.max_calls:
            self.calls[user_id].append(now)
            return True
        
        return False
    
    def reset_user(self, user_id: int):
        """Reset rate limit for a specific user"""
        if user_id in self.calls:
            del self.calls[user_id]
    
    def reset_all(self):
        """Reset all rate limits"""
        self.calls.clear()
    
    def get_remaining_time(self, user_id: int) -> float:
        """Get remaining time until user can make another call"""
        if user_id not in self.calls or not self.calls[user_id]:
            return 0
        
        now = datetime.now().timestamp()
        oldest_call = min(self.calls[user_id])
        time_until_reset = (oldest_call + self.time_window) - now
        
        return max(0, time_until_reset)

# --- Validation Functions ---
def validate_contest_id(contest_id: str) -> bool:
    """
    Validate contest ID format
    
    Rules:
    - 3-30 characters long
    - Only alphanumeric characters and hyphens
    - Cannot start or end with a hyphen
    - No consecutive hyphens
    """
    if not contest_id:
        return False
    
    if len(contest_id) < Config.MIN_CONTEST_ID_LENGTH or len(contest_id) > Config.MAX_CONTEST_ID_LENGTH:
        return False
    
    # Check format
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$', contest_id):
        # Allow single character IDs if they're alphanumeric
        if len(contest_id) == 1 and re.match(r'^[a-zA-Z0-9]$', contest_id):
            return True
        return False
    
    # No consecutive hyphens
    if '--' in contest_id:
        return False
    
    return True

def validate_song_name(song_name: str) -> bool:
    """
    Validate song name
    
    Rules:
    - 1-100 characters long
    - No control characters
    - Trimmed of leading/trailing whitespace
    """
    if not song_name:
        return False
    
    # Trim whitespace
    song_name = song_name.strip()
    
    if not song_name or len(song_name) > Config.MAX_SONG_NAME_LENGTH:
        return False
    
    # Check for control characters
    if re.search(r'[\x00-\x1F\x7F]', song_name):
        return False
    
    return True

def validate_url(url: str) -> bool:
    """
    Validate URL format
    
    Rules:
    - Must be valid HTTP(S) URL
    - Must have scheme and netloc
    - Reasonable length limit
    - No dangerous characters
    """
    if not url or len(url) > Config.MAX_URL_LENGTH:
        return False
    
    try:
        result = urlparse(url)
        
        # Check scheme
        if result.scheme not in ['http', 'https']:
            return False
        
        # Check netloc (domain)
        if not result.netloc:
            return False
        
        # Basic domain validation
        if not re.match(r'^[a-zA-Z0-9.-]+$', result.netloc.replace(':', '')):
            return False
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r'javascript:',
            r'data:',
            r'file:',
            r'ftp:',
            r'\\x',
            r'%00',
            r'<script',
            r'onclick=',
            r'onerror='
        ]
        
        url_lower = url.lower()
        for pattern in suspicious_patterns:
            if pattern in url_lower:
                return False
        
        return True
        
    except Exception:
        return False

def validate_platform_list(platforms: str, valid_platforms: List[str]) -> Optional[List[str]]:
    """
    Validate and parse platform list
    
    Args:
        platforms: Comma-separated string of platforms
        valid_platforms: List of valid platform names
    
    Returns:
        List of validated platforms or None if invalid
    """
    if not platforms:
        return None
    
    platform_list = [p.strip().lower() for p in platforms.split(',')]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_platforms = []
    for p in platform_list:
        if p not in seen and p:
            seen.add(p)
            unique_platforms.append(p)
    
    # Validate all platforms
    valid_lower = [p.lower() for p in valid_platforms]
    for platform in unique_platforms:
        if platform not in valid_lower:
            return None
    
    return unique_platforms

# --- Discord Utilities ---
def create_error_embed(title: str, message: str) -> discord.Embed:
    """Create a standardized error embed"""
    embed = discord.Embed(
        title=f"❌ {title}",
        description=message,
        color=Config.get_embed_color('error'),
        timestamp=datetime.now()
    )
    return embed

def create_success_embed(title: str, message: str = None) -> discord.Embed:
    """Create a standardized success embed"""
    embed = discord.Embed(
        title=f"✅ {title}",
        description=message,
        color=Config.get_embed_color('success'),
        timestamp=datetime.now()
    )
    return embed

def create_info_embed(title: str, description: str = None) -> discord.Embed:
    """Create a standardized info embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=Config.get_embed_color('info'),
        timestamp=datetime.now()
    )
    return embed

def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to a maximum length"""
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def format_timestamp(timestamp: datetime) -> str:
    """Format timestamp for Discord"""
    return f"<t:{int(timestamp.timestamp())}:R>"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file operations"""
    # Remove invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove control characters
    filename = re.sub(r'[\x00-\x1F\x7F]', '', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        if ext:
            name = name[:250 - len(ext)]
            filename = f"{name}.{ext}"
        else:
            filename = filename[:255]
    
    return filename

# --- String Utilities ---
def clean_user_input(text: str) -> str:
    """Clean user input for safe display"""
    if not text:
        return ""
    
    # Remove zero-width characters
    zero_width_chars = [
        '\u200b',  # Zero-width space
        '\u200c',  # Zero-width non-joiner
        '\u200d',  # Zero-width joiner
        '\ufeff',  # Zero-width no-break space
    ]
    
    for char in zero_width_chars:
        text = text.replace(char, '')
    
    # Normalize whitespace
    text = ' '.join(text.split())
    
    return text.strip()

def generate_contest_summary(contest_data: Dict[str, Any], stats: Dict[str, Any]) -> str:
    """Generate a text summary of contest data"""
    lines = [
        f"**Contest ID:** `{contest_data['contest_id']}`",
        f"**Status:** {contest_data['status'].title()}",
        f"**Created:** <t:{int(datetime.fromisoformat(contest_data['created_at']).timestamp())}:F>",
        f"**Submissions:** {stats.get('total_submissions', 0)}",
        f"**Participants:** {stats.get('unique_participants', 0)}",
    ]
    
    if contest_data.get('description'):
        lines.append(f"**Description:** {contest_data['description']}")
    
    if stats.get('platforms'):
        platform_text = ', '.join([f"{p} ({c})" for p, c in stats['platforms'].items()])
        lines.append(f"**Platforms:** {platform_text}")
    
    return '\n'.join(lines)

# --- Webhook Utilities ---
async def send_webhook_notification(
    webhook_url: str,
    title: str,
    description: str,
    color: int = None,
    fields: List[Dict[str, Any]] = None,
    author: Optional[discord.User] = None
):
    """Send a notification to a Discord webhook"""
    if not webhook_url:
        return
    
    try:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color or Config.get_embed_color('info'),
            timestamp=datetime.now()
        )
        
        if author:
            embed.set_author(
                name=str(author),
                icon_url=author.avatar.url if author.avatar else None
            )
        
        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get('name', 'Field'),
                    value=field.get('value', 'N/A'),
                    inline=field.get('inline', False)
                )
        
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)
            await webhook.send(embed=embed, username="Contest Bot")
            
    except Exception as e:
        logger.error(f"Failed to send webhook notification: {e}")

# --- Export Functions ---
async def export_contest_data(contest_id: str, format: str = 'csv') -> Optional[bytes]:
    """Export contest data in various formats"""
    from database import get_contest_stats
    import csv
    import json
    import io
    
    stats = get_contest_stats(contest_id)
    if not stats:
        return None
    
    try:
        if format == 'csv':
            output = io.StringIO()
            
            # Write contest info
            writer = csv.writer(output)
            writer.writerow(['Contest Information'])
            writer.writerow(['Field', 'Value'])
            for key, value in stats['contest'].items():
                if key not in ['public_channel_id', 'review_channel_id']:
                    writer.writerow([key, value])
            
            writer.writerow([])  # Empty row
            
            # Write submissions
            if 'votes' in stats:
                writer.writerow(['Submissions and Votes'])
                writer.writerow(['Rank', 'Song Name', 'Artist', 'Platform', 'Votes'])
                for i, sub in enumerate(stats['votes'], 1):
                    writer.writerow([
                        i,
                        sub['song_name'],
                        sub['user_name'],
                        sub['platform'],
                        sub['vote_count']
                    ])
            
            return output.getvalue().encode('utf-8')
            
        elif format == 'json':
            # Clean up data for JSON export
            export_data = {
                'contest': stats['contest'],
                'statistics': {
                    'total_submissions': stats['total_submissions'],
                    'unique_participants': stats['unique_participants'],
                    'platforms': stats['platforms']
                }
            }
            
            if 'votes' in stats:
                export_data['results'] = stats['votes']
            
            return json.dumps(export_data, indent=2).encode('utf-8')
            
    except Exception as e:
        logger.error(f"Error exporting contest data: {e}")
        return None

# --- Time Utilities ---
def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parse duration string (e.g., '1d', '2h', '30m') to timedelta"""
    match = re.match(r'^(\d+)([dhm])$', duration_str.lower())
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == 'd':
        return timedelta(days=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'm':
        return timedelta(minutes=value)
    
    return None

def format_duration(td: timedelta) -> str:
    """Format timedelta to human-readable string"""
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes and not days:  # Only show minutes if less than a day
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    
    return " ".join(parts) if parts else "less than a minute"

# --- Debug Utilities ---
def log_command_usage(ctx: discord.ApplicationContext, success: bool = True):
    """Log command usage for analytics"""
    logger.info(
        f"Command: {ctx.command.name} | "
        f"User: {ctx.author} ({ctx.author.id}) | "
        f"Guild: {ctx.guild.name if ctx.guild else 'DM'} | "
        f"Success: {success}"
    )
