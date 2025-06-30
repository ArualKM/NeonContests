# platforms.py
import re
import requests
from bs4 import BeautifulSoup

# --- Base Class for Platform Handlers ---
class PlatformHandler:
    """Base class for handling different music platforms."""
    def __init__(self, name, domains):
        self.name = name
        self.domains = domains

    def matches(self, url):
        """Check if the URL belongs to this platform."""
        return any(domain in url for domain in self.domains)

    def get_metadata(self, url):
        """Extract metadata (title, author, image) from the URL."""
        # This method should be overridden by each specific platform handler
        raise NotImplementedError

# --- Specific Platform Implementations ---

class SunoHandler(PlatformHandler):
    def __init__(self):
        super().__init__("Suno", ["suno.com"])

    def get_metadata(self, url):
        full_url, song_id = self._resolve_url_and_id(url)
        if not song_id:
            return None
        
        # Suno's title is not easily scrapable, so we rely on user input
        return {
            "id": song_id,
            "title": "Suno AI Music", # Generic title
            "author": "Suno",
            "image_url": f"https://cdn2.suno.ai/image_large_{song_id}.jpeg",
            "embed_url": full_url
        }

    def _resolve_url_and_id(self, url):
        try:
            with requests.Session() as session:
                response = session.head(url, allow_redirects=True, timeout=5)
                full_url = response.url
                if "suno.com/song/" in full_url:
                    song_id = full_url.split("suno.com/song/")[1].split("?")[0]
                    return full_url, song_id
        except requests.RequestException:
            return None, None
        return None, None

class UdioHandler(PlatformHandler):
    def __init__(self):
        super().__init__("Udio", ["udio.com"])
    
    def get_metadata(self, url):
        try:
            response = requests.get(url, timeout=5)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            title = soup.find('meta', property='og:title')
            image = soup.find('meta', property='og:image')
            
            return {
                "id": url.split('/')[-1],
                "title": title['content'] if title else "Udio Music",
                "author": "Udio",
                "image_url": image['content'] if image else None,
                "embed_url": url
            }
        except Exception:
            return None

class RiffusionHandler(PlatformHandler):
    def __init__(self):
        super().__init__("Riffusion", ["riffusion.com"])

    def get_metadata(self, url):
        try:
            response = requests.get(url, timeout=5)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            title = soup.find('meta', property='og:title')
            image = soup.find('meta', property='og:image')
            
            return {
                "id": url.split('=')[-1],
                "title": title['content'] if title else "Riffusion Music",
                "author": "Riffusion",
                "image_url": image['content'] if image else None,
                "embed_url": url
            }
        except Exception:
            return None


class YouTubeHandler(PlatformHandler):
    def __init__(self):
        super().__init__("YouTube", ["youtube.com", "youtu.be"])

    def get_metadata(self, url):
        # In a real scenario with the right tools, you would call a YouTube API here.
        # For this example, we'll simulate it by scraping meta tags.
        try:
            response = requests.get(url, timeout=5)
            soup = BeautifulSoup(response.content, 'html.parser')

            title = soup.find('meta', property='og:title')
            author = soup.find('link', itemprop='name')
            image = soup.find('meta', property='og:image')

            return {
                "id": self._get_video_id(url),
                "title": title['content'] if title else "YouTube Video",
                "author": author['content'] if author else "YouTube",
                "image_url": image['content'] if image else None,
                "embed_url": url
            }
        except Exception as e:
            print(f"Error fetching YouTube metadata: {e}")
            return None

    def _get_video_id(self, url):
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        return video_id_match.group(1) if video_id_match else None

class SoundCloudHandler(PlatformHandler):
    def __init__(self):
        super().__init__("SoundCloud", ["soundcloud.com"])

    def get_metadata(self, url):
        # SoundCloud has a public oEmbed endpoint, which is perfect for this.
        api_url = f"https://soundcloud.com/oembed?format=json&url={url}"
        try:
            response = requests.get(api_url, timeout=5)
            data = response.json()
            return {
                "id": url, # The URL is sufficient as an ID
                "title": data.get("title", "SoundCloud Track"),
                "author": data.get("author_name", "SoundCloud"),
                "image_url": data.get("thumbnail_url"),
                "embed_url": url
            }
        except Exception:
            return None

# List of all available handlers
platform_handlers = [
    SunoHandler(),
    UdioHandler(),
    RiffusionHandler(),
    YouTubeHandler(),
    SoundCloudHandler()
]

def get_platform_handler(url):
    """Finds the correct platform handler for a given URL."""
    for handler in platform_handlers:
        if handler.matches(url):
            return handler
    return None
