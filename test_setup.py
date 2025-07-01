#!/usr/bin/env python3
"""
Test script to verify bot setup and platform handlers
"""

import asyncio
import sys
from pathlib import Path

# Add project directory to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_platform_handlers():
    """Test platform URL parsing"""
    from platforms import PlatformManager
    
    print("\n🎵 Testing Platform Handlers...")
    print("-" * 40)
    
    test_urls = [
        "https://suno.com/song/test123",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://soundcloud.com/artist/track",
        "https://open.spotify.com/track/123abc",
        "https://udio.com/songs/test",
        "https://www.riffusion.com/share?id=test",
        "https://invalid-platform.com/test"
    ]
    
    manager = PlatformManager()
    
    for url in test_urls:
        handler = await manager.get_platform_handler(url)
        if handler:
            print(f"✅ {url}")
            print(f"   Platform: {handler.name}")
            
            # Try to get metadata (this might fail for test URLs)
            try:
                metadata = await manager.get_metadata(url)
                if metadata:
                    print(f"   Metadata: ID={metadata.get('id', 'N/A')}")
            except Exception as e:
                print(f"   Metadata: Failed (expected for test URLs)")
        else:
            print(f"❌ {url}")
            print(f"   Platform: Not supported")
        print()
    
    await manager.close_all()

def test_validation():
    """Test input validation functions"""
    from utils import validate_contest_id, validate_song_name, validate_url
    
    print("\n🔍 Testing Input Validation...")
    print("-" * 40)
    
    # Contest ID tests
    print("\nContest ID Validation:")
    test_ids = [
        ("summer-2025", True),
        ("test", True),
        ("a", False),  # Too short
        ("valid-contest-id", True),
        ("invalid contest", False),  # Space
        ("test!", False),  # Special char
        ("a" * 31, False),  # Too long
        ("-invalid", False),  # Starts with hyphen
        ("valid--invalid", False),  # Double hyphen
    ]
    
    for test_id, expected in test_ids:
        result = validate_contest_id(test_id)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{test_id}' -> {result} (expected {expected})")
    
    # Song name tests
    print("\nSong Name Validation:")
    test_names = [
        ("My Awesome Song", True),
        ("", False),  # Empty
        ("A" * 101, False),  # Too long
        ("Valid Song!", True),
        ("Song\x00Name", False),  # Control char
    ]
    
    for name, expected in test_names:
        result = validate_song_name(name)
        status = "✅" if result == expected else "❌"
        display_name = repr(name) if len(name) < 20 else repr(name[:20] + "...")
        print(f"{status} {display_name} -> {result} (expected {expected})")
    
    # URL tests
    print("\nURL Validation:")
    test_urls = [
        ("https://example.com", True),
        ("http://test.com/page", True),
        ("not-a-url", False),
        ("javascript:alert()", False),  # XSS attempt
        ("ftp://file.com", False),  # Wrong protocol
        ("https://" + "a" * 2000, False),  # Too long
    ]
    
    for url, expected in test_urls:
        result = validate_url(url)
        status = "✅" if result == expected else "❌"
        display_url = url if len(url) < 50 else url[:50] + "..."
        print(f"{status} {display_url} -> {result} (expected {expected})")

def test_database():
    """Test database operations"""
    from database import init_db, verify_integrity, get_db
    from config import Config
    import tempfile
    import os
    
    print("\n💾 Testing Database Operations...")
    print("-" * 40)
    
    # Use temporary database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        temp_db = tmp.name
    
    original_db = Config.DATABASE_PATH
    Config.DATABASE_PATH = temp_db
    
    try:
        # Initialize
        print("Initializing test database...")
        init_db()
        print("✅ Database initialized")
        
        # Verify
        print("Verifying integrity...")
        if verify_integrity():
            print("✅ Integrity check passed")
        else:
            print("❌ Integrity check failed")
        
        # Test basic operations
        print("Testing basic operations...")
        with get_db() as conn:
            # Insert test contest
            conn.execute(
                """INSERT INTO contests 
                   (contest_id, public_channel_id, review_channel_id, created_by) 
                   VALUES (?, ?, ?, ?)""",
                ("test-contest", 123456789, 987654321, 111111111)
            )
            
            # Query it back
            result = conn.execute(
                "SELECT * FROM contests WHERE contest_id = ?",
                ("test-contest",)
            ).fetchone()
            
            if result:
                print("✅ Insert and query successful")
            else:
                print("❌ Query failed")
    
    finally:
        # Cleanup
        Config.DATABASE_PATH = original_db
        try:
            os.unlink(temp_db)
        except:
            pass

def test_config():
    """Test configuration loading"""
    from config import Config
    
    print("\n⚙️  Testing Configuration...")
    print("-" * 40)
    
    # Check required config
    if Config.DISCORD_TOKEN:
        print("✅ Discord token loaded")
    else:
        print("❌ Discord token not found")
    
    # Display some config values
    print(f"Database: {Config.DATABASE_PATH}")
    print(f"Rate limit: {Config.RATE_LIMIT_SUBMISSIONS} per {Config.RATE_LIMIT_WINDOW}s")
    print(f"Max song name: {Config.MAX_SONG_NAME_LENGTH} chars")
    print(f"Log level: {Config.LOG_LEVEL}")

async def main():
    """Run all tests"""
    print("🔧 Discord Music Contest Bot - Setup Test")
    print("=" * 45)
    
    # Test configuration
    test_config()
    
    # Test validation
    test_validation()
    
    # Test database
    test_database()
    
    # Test platform handlers
    await test_platform_handlers()
    
    print("\n✅ All tests completed!")
    print("\nIf all tests passed, your bot is ready to run!")
    print("Start with: python run.py")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
