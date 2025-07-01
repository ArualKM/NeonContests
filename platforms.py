# platforms.py - Secure async platform handlers

import re
import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote
from typing import Optional, Dict, Any
from functools import lru_cache

logger = logging.getLogger('platform_handlers')

# Configuration
MAX_RESPONSE_SIZE = 1024 * 1024  # 1MB
REQUEST_TIMEOUT = 5
USER_AGENT = 'Discord Music Contest Bot/1.0'

# --- Base Platform Handler ---
class AsyncPlatformHandler:
    """Base class for handling different music platforms asynchronously"""
    
    def __init__(self, name: str, domains: list):
        self.name = name
        self.domains = domains
        self._session = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'User-Agent': USER_AGENT}
            )
        return self._session
    
    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def matches(self, url: str) -> bool:
        """Check if the URL belongs to this platform"""
        try:
            parsed = urlparse(url)
            return any(domain in parsed.netloc for domain in self.domains)
        except:
            return False
    
    def sanitize_url(self, url: str) -> Optional[str]:
        """Validate and sanitize URL"""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ['http', 'https']:
                return None
            if not parsed.netloc:
                return None
            # Rebuild URL to ensure it's clean
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except:
            return None
    
    async def fetch_with_limit(self, url: str) -> Optional[str]:
        """Fetch URL content with size limit"""
        clean_url = self.sanitize_url(url)
        if not clean_url:
            logger.warning(f"Invalid URL: {url}")
            return None
        
        try:
            session = await self.get_session()
            async with session.get(clean_url) as response:
                # Check status
                if response.status != 200:
                    logger.warning(f"HTTP {response.status} for {clean_url}")
                    return None
                
                # Check content length
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > MAX_RESPONSE_SIZE:
                    logger.warning(f"Response too large: {content_length} bytes")
                    return None
                
                # Read with size limit
                content = await response.text(encoding='utf-8')
                if len(content) > MAX_RESPONSE_SIZE:
                    logger.warning(f"Content exceeds size limit")
                    return None
                
                return content
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {clean_url}")
        except aiohttp.ClientError as e:
            logger.error(f"Client error fetching {clean_url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching {clean_url}: {e}")
        
        return None
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract metadata - to be implemented by subclasses"""
        raise NotImplementedError

# --- Suno Handler ---
class SunoHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("Suno", ["suno.com", "suno.ai"])
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        # First, resolve the URL to get the song ID
        song_id = await self._resolve_song_id(url)
        if not song_id:
            return None
        
        # Validate song ID format
        if not re.match(r'^[a-zA-Z0-9_-]+$', song_id):
            logger.warning(f"Invalid Suno song ID: {song_id}")
            return None
        
        return {
            "id": song_id,
            "title": "Suno AI Music",
            "author": "Suno",
            "image_url": f"https://cdn2.suno.ai/image_large_{song_id}.jpeg",
            "embed_url": f"https://suno.com/song/{song_id}"
        }
    
    async def _resolve_song_id(self, url: str) -> Optional[str]:
        """Resolve short URLs and extract song ID"""
        try:
            session = await self.get_session()
            async with session.head(url, allow_redirects=True) as response:
                final_url = str(response.url)
                
                # Extract song ID from URL
                match = re.search(r'suno\.(?:com|ai)/song/([a-zA-Z0-9_-]+)', final_url)
                if match:
                    return match.group(1)
                    
        except Exception as e:
            logger.error(f"Error resolving Suno URL: {e}")
        
        return None

# --- YouTube Handler ---
class YouTubeHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("YouTube", ["youtube.com", "youtu.be", "m.youtube.com"])
    
    @lru_cache(maxsize=100)
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats"""
        patterns = [
            r'(?:v=|/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed/)([0-9A-Za-z_-]{11})',
            r'(?:watch\?.*v=)([0-9A-Za-z_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        video_id = self._extract_video_id(url)
        if not video_id:
            logger.warning(f"Could not extract YouTube video ID from {url}")
            return None
        
        # Use YouTube's oEmbed endpoint (no API key required)
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        
        try:
            session = await self.get_session()
            async with session.get(oembed_url) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                return {
                    "id": video_id,
                    "title": data.get("title", "YouTube Video"),
                    "author": data.get("author_name", "YouTube"),
                    "image_url": data.get("thumbnail_url"),
                    "embed_url": f"https://www.youtube.com/watch?v={video_id}"
                }
                
        except Exception as e:
            logger.error(f"Error fetching YouTube metadata: {e}")
            
        # Fallback to HTML scraping
        return await self._scrape_metadata(url)
    
    async def _scrape_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Fallback HTML scraping for metadata"""
        content = await self.fetch_with_limit(url)
        if not content:
            return None
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            title = soup.find('meta', property='og:title')
            image = soup.find('meta', property='og:image')
            
            return {
                "id": self._extract_video_id(url),
                "title": title.get('content') if title else "YouTube Video",
                "author": "YouTube",
                "image_url": image.get('content') if image else None,
                "embed_url": url
            }
        except Exception as e:
            logger.error(f"Error parsing YouTube HTML: {e}")
            return None

# --- SoundCloud Handler ---
class SoundCloudHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("SoundCloud", ["soundcloud.com"])
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        # SoundCloud has a public oEmbed endpoint
        oembed_url = f"https://soundcloud.com/oembed?format=json&url={quote(url)}"
        
        try:
            session = await self.get_session()
            async with session.get(oembed_url) as response:
                if response.status != 200:
                    logger.warning(f"SoundCloud oEmbed returned {response.status}")
                    return None
                
                data = await response.json()
                
                # Extract track ID from the embed code
                track_id = None
                if 'html' in data:
                    match = re.search(r'/tracks/(\d+)', data['html'])
                    if match:
                        track_id = match.group(1)
                
                return {
                    "id": track_id or url,
                    "title": data.get("title", "SoundCloud Track"),
                    "author": data.get("author_name", "SoundCloud"),
                    "image_url": data.get("thumbnail_url"),
                    "embed_url": url
                }
                
        except Exception as e:
            logger.error(f"Error fetching SoundCloud metadata: {e}")
            return None

# --- Platform Manager ---
class PlatformManager:
    """Manages all platform handlers"""
    
    def __init__(self):
        self.handlers = [
            SunoHandler(),
            YouTubeHandler(),
            SoundCloudHandler(),
            # Add more handlers here
        ]
    
    async def get_platform_handler(self, url: str) -> Optional[AsyncPlatformHandler]:
        """Find the correct platform handler for a URL"""
        for handler in self.handlers:
            if handler.matches(url):
                return handler
        return None
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Get metadata for any supported platform"""
        handler = await self.get_platform_handler(url)
        if not handler:
            return None
        
        try:
            return await handler.get_metadata(url)
        except Exception as e:
            logger.error(f"Error getting metadata for {url}: {e}")
            return None
    
    async def close_all(self):
        """Close all handler sessions"""
        for handler in self.handlers:
            await handler.close()

# --- Usage Example ---
async def example_usage():
    manager = PlatformManager()
    
    try:
        # Get metadata for a URL
        metadata = await manager.get_metadata("https://suno.com/song/example")
        if metadata:
            print(f"Title: {metadata['title']}")
            print(f"Author: {metadata['author']}")
            print(f"Image: {metadata['image_url']}")
    finally:
        # Always close sessions
        await manager.close_all()

# For backwards compatibility with sync code
def get_platform_handler(url: str) -> Optional[Dict[str, str]]:
    """Sync wrapper for async platform handlers"""
    async def _get():
        manager = PlatformManager()
        try:
            handler = await manager.get_platform_handler(url)
            return handler
        finally:
            await manager.close_all()
    
    try:
        return asyncio.run(_get())
    except:
        return None
