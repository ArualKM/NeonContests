# platforms.py - Async platform handlers for music services
import re
import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote
from typing import Optional, Dict, Any, List
from functools import lru_cache
from config import Config

logger = logging.getLogger('platform_handlers')

# --- Base Platform Handler ---
class AsyncPlatformHandler:
    """Base class for handling different music platforms asynchronously"""
    
    def __init__(self, name: str, domains: List[str]):
        self.name = name
        self.domains = domains
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'User-Agent': f"{Config.USER_AGENT} (bot)"} # More descriptive user agent
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
        except Exception:
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
        except Exception:
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
                # Handle success case first
                if response.status == 200:
                    # Check content length
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > Config.MAX_RESPONSE_SIZE:
                        logger.warning(f"Response too large: {content_length} bytes for {clean_url}")
                        return None
                    
                    # Read with size limit
                    content = await response.text(encoding='utf-8')
                    if len(content) > Config.MAX_RESPONSE_SIZE:
                        logger.warning(f"Content from {clean_url} exceeds size limit")
                        return None
                    
                    return content
                
                # Handle error statuses
                if response.status == 403:
                    logger.warning(f"HTTP 403 Forbidden for {clean_url}. Riffusion may be blocking requests.")
                else:
                    logger.warning(f"HTTP {response.status} for {clean_url}")
                return None
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {clean_url}")
        except aiohttp.ClientError as e:
            logger.error(f"Client error fetching {clean_url}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching {clean_url}: {e}")
        
        return None

    async def polite_fetch(self, url:str):
        await asyncio.sleep(1) # Respectful Delay
        return await self.fetch_with_limit(url)
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract metadata - to be implemented by subclasses"""
        raise NotImplementedError
    
    def get_embed_url(self, url: str) -> str:
        """Get embeddable URL - default implementation"""
        return url

# --- Suno Handler ---
class SunoHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("Suno", ["suno.com", "suno.ai"])
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        # First, resolve the URL to get the song ID
        song_id = await self._resolve_song_id(url)
        if not song_id:
            logger.warning(f"Could not extract Suno song ID from {url}")
            return None
        
        # Validate song ID format
        if not re.match(r'^[a-zA-Z0-9_-]+$', song_id):
            logger.warning(f"Invalid Suno song ID format: {song_id}")
            return None
        
        # Construct canonical URL
        embed_url = f"https://suno.com/song/{song_id}"
        
        return {
            "id": song_id,
            "title": "Suno AI Music",
            "author": "Suno AI",
            "image_url": f"https://cdn2.suno.ai/image_large_{song_id}.jpeg",
            "embed_url": embed_url
        }
    
    async def _resolve_song_id(self, url: str) -> Optional[str]:
        """Resolve short URLs and extract song ID"""
        try:
            # First try to extract from URL directly
            patterns = [
                r'suno\.(?:com|ai)/song/([a-zA-Z0-9_-]+)',
                r'suno\.(?:com|ai)/.*[?&]id=([a-zA-Z0-9_-]+)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            
            # If not found, try following redirects
            session = await self.get_session()
            async with session.head(url, allow_redirects=True) as response:
                final_url = str(response.url)
                
                # Try patterns again on final URL
                for pattern in patterns:
                    match = re.search(pattern, final_url)
                    if match:
                        return match.group(1)
                    
        except Exception as e:
            logger.error(f"Error resolving Suno URL: {e}")
        
        return None

# --- Udio Handler ---
class UdioHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("Udio", ["udio.com"])
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        content = await self.fetch_with_limit(url)
        if not content:
            return None
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract metadata from meta tags
            title = soup.find('meta', property='og:title')
            image = soup.find('meta', property='og:image')
            description = soup.find('meta', property='og:description')
            
            # Extract ID from URL
            song_id = url.rstrip('/').split('/')[-1]
            
            return {
                "id": song_id,
                "title": title.get('content') if title else "Udio Music",
                "author": "Udio",
                "image_url": image.get('content') if image else None,
                "embed_url": url,
                "description": description.get('content') if description else None
            }
        except Exception as e:
            logger.error(f"Error parsing Udio metadata: {e}")
            return None

# --- Riffusion Handler ---
class RiffusionHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("Riffusion", ["riffusion.com", "www.riffusion.com"])
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        content = await self.polite_fetch(url)
        if not content:
            return None
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            title = soup.find('meta', property='og:title')
            image = soup.find('meta', property='og:image')
            
            # Extract ID from URL parameters
            song_id = None
            if '=' in url:
                song_id = url.split('=')[-1]
            
            return {
                "id": song_id or url,
                "title": title.get('content') if title else "Riffusion Music",
                "author": "Riffusion",
                "image_url": image.get('content') if image else None,
                "embed_url": url
            }
        except Exception as e:
            logger.error(f"Error parsing Riffusion metadata: {e}")
            return None

# --- YouTube Handler ---
class YouTubeHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("YouTube", ["youtube.com", "youtu.be", "m.youtube.com", "www.youtube.com"])
    
    @lru_cache(maxsize=100)
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats"""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/)([0-9A-Za-z_-]{11})',
            r'(?:youtube\.com/embed/)([0-9A-Za-z_-]{11})',
            r'(?:youtube\.com/v/)([0-9A-Za-z_-]{11})',
            r'(?:youtube\.com/shorts/)([0-9A-Za-z_-]{11})'
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
                if response.status == 200:
                    data = await response.json()
                    return {
                        "id": video_id,
                        "title": data.get("title", "YouTube Video"),
                        "author": data.get("author_name", "YouTube"),
                        "image_url": data.get("thumbnail_url"),
                        "embed_url": f"https://www.youtube.com/watch?v={video_id}"
                    }
                else:
                    logger.warning(f"YouTube oEmbed returned status {response.status}")
                    
        except Exception as e:
            logger.error(f"Error fetching YouTube metadata: {e}")
        
        # Fallback to HTML scraping
        return await self._scrape_metadata(url, video_id)
    
    async def _scrape_metadata(self, url: str, video_id: str) -> Optional[Dict[str, Any]]:
        """Fallback HTML scraping for metadata"""
        content = await self.fetch_with_limit(url)
        if not content:
            return None
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            title = soup.find('meta', property='og:title')
            image = soup.find('meta', property='og:image')
            
            return {
                "id": video_id,
                "title": title.get('content') if title else "YouTube Video",
                "author": "YouTube",
                "image_url": image.get('content') if image else f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                "embed_url": f"https://www.youtube.com/watch?v={video_id}"
            }
        except Exception as e:
            logger.error(f"Error parsing YouTube HTML: {e}")
            return None

# --- SoundCloud Handler ---
class SoundCloudHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("SoundCloud", ["soundcloud.com", "www.soundcloud.com"])
    
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
                
                # Extract track ID from the embed code if available
                track_id = None
                if 'html' in data:
                    match = re.search(r'/tracks/(\d+)', data['html'])
                    if match:
                        track_id = match.group(1)
                
                return {
                    "id": track_id or url,
                    "title": data.get("title", "SoundCloud Track"),
                    "author": data.get("author_name", "SoundCloud Artist"),
                    "image_url": data.get("thumbnail_url"),
                    "embed_url": url,
                    "duration": data.get("duration")
                }
                
        except Exception as e:
            logger.error(f"Error fetching SoundCloud metadata: {e}")
            return None

# --- Spotify Handler (Optional) ---
class SpotifyHandler(AsyncPlatformHandler):
    def __init__(self):
        super().__init__("Spotify", ["open.spotify.com", "spotify.com"])
    
    def _extract_track_id(self, url: str) -> Optional[str]:
        """Extract track ID from Spotify URL"""
        match = re.search(r'track/([a-zA-Z0-9]+)', url)
        return match.group(1) if match else None
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        track_id = self._extract_track_id(url)
        if not track_id:
            return None
        
        # Note: Full Spotify metadata requires API authentication
        # This is a basic implementation
        return {
            "id": track_id,
            "title": "Spotify Track",
            "author": "Spotify Artist",
            "image_url": None,
            "embed_url": url
        }

# --- Platform Manager ---
class PlatformManager:
    """Manages all platform handlers"""
    
    def __init__(self):
        self.handlers = [
            SunoHandler(),
            UdioHandler(),
            RiffusionHandler(),
            YouTubeHandler(),
            SoundCloudHandler(),
            SpotifyHandler(),
        ]
        self._handler_cache = {}
    
    async def get_platform_handler(self, url: str) -> Optional[AsyncPlatformHandler]:
        """Find the correct platform handler for a URL"""
        # Check cache first
        if url in self._handler_cache:
            return self._handler_cache[url]
        
        for handler in self.handlers:
            if handler.matches(url):
                self._handler_cache[url] = handler
                return handler
        return None
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Get metadata for any supported platform"""
        handler = await self.get_platform_handler(url)
        if not handler:
            logger.warning(f"No handler found for URL: {url}")
            return None
        
        try:
            metadata = await handler.get_metadata(url)
            if metadata:
                # Add platform name to metadata
                metadata['platform'] = handler.name
            return metadata
        except Exception as e:
            logger.error(f"Error getting metadata for {url}: {e}")
            return None
    
    async def close_all(self):
        """Close all handler sessions"""
        for handler in self.handlers:
            try:
                await handler.close()
            except Exception as e:
                logger.error(f"Error closing {handler.name} handler: {e}")
    
    def get_supported_platforms(self) -> List[str]:
        """Get list of supported platform names"""
        return [handler.name for handler in self.handlers]
    
    def clear_cache(self):
        """Clear the handler cache"""
        self._handler_cache.clear()

# --- Utility Functions ---
async def test_platform_url(url: str) -> Dict[str, Any]:
    """Test a URL and return platform info and metadata"""
    manager = PlatformManager()
    try:
        handler = await manager.get_platform_handler(url)
        if not handler:
            return {"error": "Unsupported platform"}
        
        metadata = await manager.get_metadata(url)
        if not metadata:
            return {"error": "Could not fetch metadata"}
        
        return {
            "platform": handler.name,
            "metadata": metadata,
            "success": True
        }
    finally:
        await manager.close_all()

# For backwards compatibility with sync code
def get_platform_handler(url: str) -> Optional[Dict[str, str]]:
    """Sync wrapper for async platform handlers - DEPRECATED"""
    async def _get():
        manager = PlatformManager()
        try:
            handler = await manager.get_platform_handler(url)
            return handler
        finally:
            await manager.close_all()
    
    try:
        import asyncio
        return asyncio.run(_get())
    except Exception:
        return None
