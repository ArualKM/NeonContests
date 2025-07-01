# 🎵 Discord Music Contest Bot - Production Ready

A powerful, secure, and feature-rich Discord bot for running music submission contests. Supports multiple platforms, includes comprehensive admin controls, voting systems, and robust security features.

## ✨ Features

### Core Features
- **Multi-Platform Support**: Suno, Udio, Riffusion, YouTube, SoundCloud, Spotify
- **Contest Management**: Create, edit, and manage multiple contests simultaneously
- **Anonymous Voting**: Fair voting system with submissions posted anonymously
- **Dual-Channel System**: Public channel for voting, private channel for admin review
- **Rate Limiting**: Protection against spam and abuse
- **Comprehensive Logging**: Full audit trail of all actions

### Advanced Features
- **Database Migrations**: Automatic schema updates without data loss
- **Automatic Backups**: Scheduled database backups with retention policy
- **Contest Statistics**: Detailed analytics and leaderboards
- **Export Functionality**: Export contest data as CSV or JSON
- **Platform Validation**: Ensure submissions come from allowed platforms only
- **Async Architecture**: Non-blocking I/O for optimal performance
- **Error Recovery**: Graceful error handling with detailed logging

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Discord account with a server where you have admin privileges
- Basic knowledge of Discord bot setup

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/discord-music-contest-bot.git
cd discord-music-contest-bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your Discord bot token
```

4. **Create Discord Bot**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application and bot
   - Copy the bot token to your `.env` file
   - Enable these Privileged Gateway Intents:
     - Server Members Intent
     - Message Content Intent

5. **Invite Bot to Server**
   - In the Developer Portal, go to OAuth2 > URL Generator
   - Select scopes: `bot`, `applications.commands`
   - Select permissions:
     - Send Messages
     - Manage Messages
     - Embed Links
     - Read Message History
     - Add Reactions
     - Use Slash Commands
   - Use the generated URL to invite the bot

6. **Run the bot**
```bash
python main.py
```

## 📋 Commands

### User Commands

#### `/submit`
Submit a track to a contest
- `contest_id`: The contest identifier
- `song_name`: Your track's name (max 100 characters)
- `url`: URL from a supported platform

#### `/submission list`
View all your submissions
- `contest_id` (optional): Filter by specific contest

#### `/submission delete`
Delete one of your submissions
- `submission_id`: The ID of the submission to delete

#### `/contest stats`
View contest statistics and current leaderboard
- `contest_id`: The contest to view

#### `/help`
Get help with bot commands

### Admin Commands

#### `/contest create`
Create a new contest
- `contest_id`: Unique identifier (3-30 chars, alphanumeric + hyphens)
- `public_channel`: Channel for anonymous submissions
- `review_channel`: Private channel for admin review
- `allowed_platforms` (optional): Comma-separated list (e.g., "suno,youtube")
- `submission_limit` (optional): Max submissions per user (1-10, default: 1)
- `description` (optional): Contest description

#### `/contest edit`
Modify an existing contest
- `contest_id`: Contest to edit
- `public_channel` (optional): New public channel
- `review_channel` (optional): New review channel
- `submission_limit` (optional): New submission limit
- `status` (optional): Change status (active/voting/closed)

#### `/contest delete`
Delete a contest and all submissions
- `contest_id`: Contest to delete

## 🔒 Security Features

### Input Validation
- **Contest IDs**: Alphanumeric + hyphens only, 3-30 characters
- **Song Names**: Max 100 characters, no control characters
- **URLs**: Validated for proper format and safety
- **Platform Lists**: Validated against supported platforms

### Rate Limiting
- Configurable per-action rate limits
- Automatic cleanup of old rate limit data
- Per-user tracking to prevent abuse

### Database Security
- SQL injection prevention via parameterized queries
- Foreign key constraints for data integrity
- Automatic backups with configurable retention
- Transaction support for atomic operations

### Permission System
- Role-based access control
- Separate permissions for contest management
- Admin override capabilities
- Audit logging of all actions

## 🗂️ File Structure

```
discord-music-contest-bot/
├── main.py              # Main bot file
├── config.py            # Configuration management
├── database.py          # Database operations
├── platforms.py         # Platform handlers
├── utils.py             # Utility functions
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
├── README.md            # Documentation
├── bot.log              # Runtime logs
├── suno_contests.db     # SQLite database
└── backups/             # Database backups
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_TOKEN` | **Required** - Bot token | None |
| `DATABASE_PATH` | Database file location | `suno_contests.db` |
| `BACKUP_DIR` | Backup directory | `backups` |
| `MAX_BACKUPS` | Number of backups to keep | `10` |
| `RATE_LIMIT_SUBMISSIONS` | Submissions per minute | `5` |
| `RATE_LIMIT_WINDOW` | Rate limit window (seconds) | `60` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_WEBHOOK_URL` | Discord webhook for logs | None |
| `ENABLE_VOTING` | Enable voting system | `true` |

### Database Schema

The bot uses SQLite with the following main tables:
- `contests`: Contest configuration and metadata
- `submissions`: User submissions with platform data
- `votes`: Vote tracking for submissions
- `audit_log`: Complete action history
- `rate_limits`: Rate limiting data

## 🎯 Usage Examples

### Creating a Contest
```
/contest create
  contest_id: summer-beats-2025
  public_channel: #music-contest
  review_channel: #contest-admin
  allowed_platforms: suno,udio
  submission_limit: 2
  description: Summer music creation contest!
```

### Submitting a Track
```
/submit
  contest_id: summer-beats-2025
  song_name: Sunset Vibes
  url: https://suno.com/song/abc123
```

### Viewing Contest Stats
```
/contest stats
  contest_id: summer-beats-2025
```

## 🔧 Advanced Configuration

### Custom Role Permissions
Edit the `is_contest_manager()` function in `main.py`:
```python
def is_contest_manager():
    async def predicate(ctx):
        # Add your custom role names here
        allowed_roles = ["Contest Manager", "Moderator", "DJ"]
        user_roles = [role.name for role in ctx.author.roles]
        return any(role in allowed_roles for role in user_roles) or \
               ctx.author.guild_permissions.administrator
    return commands.check(predicate)
```

### Adding New Platforms
Add a new handler class in `platforms.py`:
```python
class MyPlatformHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("MyPlatform", ["myplatform.com"])
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        # Implement metadata extraction
        pass
```

### Webhook Notifications
Set up webhooks for monitoring:
1. Create a webhook in your Discord server
2. Add the URL to your `.env` file:
   ```
   LOG_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ERROR_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```

## 📊 Monitoring & Maintenance

### Health Checks
- Check `bot.log` for runtime information
- Monitor database size and run vacuum if needed
- Review audit logs for suspicious activity

### Database Maintenance
```python
# Run these commands periodically
from database import vacuum_database, analyze_database, verify_integrity

# Optimize database
vacuum_database()
analyze_database()

# Verify integrity
if verify_integrity():
    print("Database is healthy")
```

### Backup Management
- Automatic daily backups via background task
- Manual backup: `python -c "from database import create_backup; create_backup()"`
- Backups stored in `backups/` directory

## 🐛 Troubleshooting

### Common Issues

1. **"Bot lacks permissions"**
   - Ensure bot has all required permissions in both channels
   - Check channel-specific permission overrides

2. **"Rate limit exceeded"**
   - Default: 5 submissions per minute
   - Adjust `RATE_LIMIT_SUBMISSIONS` in `.env`

3. **"Invalid contest ID"**
   - Use only letters, numbers, and hyphens
   - 3-30 characters long

4. **Platform not recognized**
   - Check URL format is correct
   - Ensure platform is in supported list

### Debug Mode
Enable debug logging:
```bash
LOG_LEVEL=DEBUG python main.py
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- Discord.py community for excellent documentation
- Contributors and testers
- Music platform APIs for metadata access

## 📞 Support

- Create an issue on GitHub
- Join our Discord server: [invite link]
- Check the wiki for detailed guides

---

Made with ❤️ for the music creation community
