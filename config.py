# config.py - Configuration settings for the Discord Music Contest Bot
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    """Central configuration for the bot"""
    
    # Discord
    DISCORD_TOKEN: str = os.getenv('DISCORD_TOKEN', '')
    
    # Database
    DATABASE_PATH: str = os.getenv('DATABASE_PATH', 'suno_contests.db')
    BACKUP_DIR: str = os.getenv('BACKUP_DIR', 'backups')
    MAX_BACKUPS: int = int(os.getenv('MAX_BACKUPS', '10'))
    
    # Validation limits
    MAX_SONG_NAME_LENGTH: int = 100
    MIN_CONTEST_ID_LENGTH: int = 3
    MAX_CONTEST_ID_LENGTH: int = 30
    MAX_URL_LENGTH: int = 2048
    MAX_DESCRIPTION_LENGTH: int = 1000
    
    # Rate limiting
    RATE_LIMIT_SUBMISSIONS: int = int(os.getenv('RATE_LIMIT_SUBMISSIONS', '5'))
    RATE_LIMIT_WINDOW: int = int(os.getenv('RATE_LIMIT_WINDOW', '60'))  # seconds
    RATE_LIMIT_DELETIONS: int = int(os.getenv('RATE_LIMIT_DELETIONS', '10'))
    
    # Request settings
    REQUEST_TIMEOUT: int = int(os.getenv('REQUEST_TIMEOUT', '5'))
    MAX_RESPONSE_SIZE: int = int(os.getenv('MAX_RESPONSE_SIZE', str(1024 * 1024)))  # 1MB
    USER_AGENT: str = 'Discord Music Contest Bot/2.0'
    
    # Contest defaults
    DEFAULT_SUBMISSION_LIMIT: int = 1
    MAX_SUBMISSION_LIMIT: int = 10
    
    # Logging
    LOG_FILE: str = os.getenv('LOG_FILE', 'bot.log')
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    
    # Webhook for monitoring (optional)
    LOG_WEBHOOK_URL: Optional[str] = os.getenv('LOG_WEBHOOK_URL')
    ERROR_WEBHOOK_URL: Optional[str] = os.getenv('ERROR_WEBHOOK_URL')
    
    # Features
    ENABLE_VOTING: bool = os.getenv('ENABLE_VOTING', 'true').lower() == 'true'
    ENABLE_ANALYTICS: bool = os.getenv('ENABLE_ANALYTICS', 'false').lower() == 'true'
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        config = cls()
        
        if not config.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is required in environment variables")
        
        if config.MAX_SONG_NAME_LENGTH < 10:
            raise ValueError("MAX_SONG_NAME_LENGTH must be at least 10")
        
        if config.MIN_CONTEST_ID_LENGTH > config.MAX_CONTEST_ID_LENGTH:
            raise ValueError("MIN_CONTEST_ID_LENGTH cannot be greater than MAX_CONTEST_ID_LENGTH")
        
        return True
    
    @classmethod
    def get_embed_color(cls, color_type: str) -> int:
        """Get Discord embed colors"""
        colors = {
            'success': 0x00ff00,  # Green
            'error': 0xff0000,    # Red
            'warning': 0xffa500,  # Orange
            'info': 0x0099ff,     # Blue
            'primary': 0x5865f2,  # Discord Blurple
        }
        return colors.get(color_type, colors['primary'])

# Validate configuration on import
Config.validate()
