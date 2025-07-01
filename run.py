#!/usr/bin/env python3
"""
Discord Music Contest Bot - Startup Script
This script performs pre-flight checks and starts the bot
"""

import sys
import os
import logging
from pathlib import Path

# Add project directory to path
sys.path.insert(0, str(Path(__file__).parent))

def check_python_version():
    """Ensure Python 3.8+"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required!")
        print(f"Current version: {sys.version}")
        sys.exit(1)

def check_dependencies():
    """Check if required packages are installed"""
    required_packages = {
        'discord': 'py-cord',
        'dotenv': 'python-dotenv',
        'aiohttp': 'aiohttp',
        'bs4': 'beautifulsoup4'
    }
    
    missing = []
    for module, package in required_packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    
    if missing:
        print("❌ Missing required packages:")
        for package in missing:
            print(f"  - {package}")
        print("\nInstall with: pip install -r requirements.txt")
        sys.exit(1)

def check_environment():
    """Check environment configuration"""
    from dotenv import load_dotenv
    
    # Load environment variables
    env_path = Path('.env')
    if not env_path.exists():
        print("❌ .env file not found!")
        print("Copy .env.example to .env and add your Discord token")
        sys.exit(1)
    
    load_dotenv()
    
    token = os.getenv('DISCORD_TOKEN')
    if not token or token == 'your_discord_bot_token_here':
        print("❌ DISCORD_TOKEN not set in .env file!")
        print("Get your bot token from https://discord.com/developers/applications")
        sys.exit(1)
    
    return True

def setup_logging():
    """Configure logging"""
    from config import Config
    
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(log_format)
    console_handler.setFormatter(console_formatter)
    
    # File handler
    file_handler = logging.FileHandler(Config.LOG_FILE)
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(log_format)
    file_handler.setFormatter(file_formatter)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    return logging.getLogger('startup')

def initialize_database():
    """Initialize database if needed"""
    from database import init_db, migrate_db, verify_integrity
    
    logger = logging.getLogger('startup')
    
    try:
        logger.info("Initializing database...")
        init_db()
        
        logger.info("Running migrations...")
        migrate_db()
        
        logger.info("Verifying database integrity...")
        if not verify_integrity():
            logger.error("Database integrity check failed!")
            return False
        
        logger.info("Database ready!")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False

def print_startup_banner():
    """Print startup banner"""
    banner = """
╔═══════════════════════════════════════════╗
║      🎵 Discord Music Contest Bot 🎵      ║
║            Production Ready               ║
╚═══════════════════════════════════════════╝
    """
    print(banner)

def main():
    """Main startup function"""
    print_startup_banner()
    
    print("🔍 Checking Python version...")
    check_python_version()
    print("✅ Python version OK")
    
    print("\n🔍 Checking dependencies...")
    check_dependencies()
    print("✅ All dependencies installed")
    
    print("\n🔍 Checking environment...")
    check_environment()
    print("✅ Environment configured")
    
    print("\n🔧 Setting up logging...")
    logger = setup_logging()
    print("✅ Logging configured")
    
    print("\n💾 Initializing database...")
    if not initialize_database():
        print("❌ Database initialization failed! Check logs for details.")
        sys.exit(1)
    print("✅ Database initialized")
    
    print("\n🚀 Starting bot...")
    print("-" * 45)
    
    try:
        # Import and run the main bot
        from main import bot, TOKEN
        
        # Log supported platforms
        from platforms import PlatformManager
        pm = PlatformManager()
        logger.info(f"Supported platforms: {', '.join(pm.get_supported_platforms())}")
        
        # Start the bot
        bot.run(TOKEN)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Bot stopped by user")
        logger.info("Bot stopped by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
