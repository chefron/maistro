from datetime import datetime
from dotenv import load_dotenv
import os
from maistro.core.memory.manager import MemoryManager
from maistro.integrations.platforms.soundcloud.soundcloud import get_user_tracks_data, format_track_stats
from maistro.integrations.platforms.youtube.youtube import get_youtube_channel_stats, get_channel_videos, format_video_stats
from maistro.integrations.platforms.spotify.spotify import get_spotify_artist_stats, format_artist_stats
from maistro.integrations.platforms.dexscreener.dexscreener import get_token_data, format_token_stats

import logging
logger = logging.getLogger('maistro.core.analytics')
        
load_dotenv()

class PlatformStats:
    """Handles gathering and storing platform-specific stats"""
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager

    def update_soundcloud_stats(self, user_id: str = None, client_id: str = None) -> bool:
        """Fetch, format, and store SoundCloud stats"""
        user_id = user_id or os.getenv('SOUNDCLOUD_USER_ID')
        client_id = client_id or os.getenv('SOUNDCLOUD_CLIENT_ID')

        try:
            tracks_info = get_user_tracks_data(user_id, client_id)
            if not tracks_info:
                return False
            
            formatted_stats = format_track_stats(tracks_info)
            print(formatted_stats)

            metadata = {
                "platform": "soundcloud",
                "timestamp": datetime.now().isoformat(),
                "source": "soundcloud_stats",
                "content_type": "performance_metrics",
            }

            memory_ids = self.memory_manager.create_chunks(
                category="metrics",
                direct_content=formatted_stats,
                content_type="metrics",
                metadata=metadata
            )
            
            return bool(memory_ids)
        
        except Exception as e:
            logger.error(f"Error updating SoundCloud stats: {e}")
            return False
    
    def update_youtube_stats(self, channel_id:str = None, api_key: str = None) -> bool:
        """Fetch, format, and store YouTube stats"""
        channel_id = channel_id or os.getenv('YOUTUBE_CHANNEL_ID')
        api_key = api_key or os.getenv('YOUTUBE_API_KEY')
        
        try:
            channel_stats = get_youtube_channel_stats(channel_id, api_key)
            if not channel_stats:
                return False
            
            videos_info = get_channel_videos(channel_id, api_key)
            if not videos_info:
                return False
            
            formatted_stats = format_video_stats(channel_stats, videos_info)
            print(formatted_stats)

            metadata = {
            "platform": "youtube",
            "timestamp": datetime.now().isoformat(),
            "source": "youtube_stats",
            "content_type": "performance_metrics"
            }
        
            memory_ids = self.memory_manager.create_chunks(
                category="metrics",
                direct_content=formatted_stats,
                content_type="metrics",
                metadata=metadata
            )
            
            return bool(memory_ids)
        
        except Exception as e:
            logger.error(f"Error updating YouTube stats: {e}")
            return False

    def update_spotify_stats(self, artist_id: str = None, client_id: str = None, client_secret: str = None ) -> bool:
        """Fetch, format, and store spotify stats"""
        artist_id = artist_id or os.getenv('SPOTIFY_ARTIST_ID')
        client_id = client_id or os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = client_secret or os.getenv('SPOTIFY_CLIENT_SECRET')

        try:
            artist_stats = get_spotify_artist_stats(artist_id, client_id, client_secret)
            if not artist_stats:
                return False
            
            formatted_stats = format_artist_stats(artist_stats)
            print(formatted_stats)

            metadata = {
                "platform": "spotify",
                "timestamp": datetime.now().isoformat(),
                "source": "spotify_stats",
                "content_type": "performance_metrics",
            }

            memory_ids = self.memory_manager.create_chunks(
                category="metrics",
                direct_content=formatted_stats,
                content_type="metrics",
                metadata=metadata
            )
            
            return bool(memory_ids)
        
        except Exception as e:
            logger.error(f"Error updating Spotify stats: {e}")
            return False
        
    def update_token_stats(self, chain_id: str = None, token_address: str = None) -> bool:
        """Fetch, format, and store token stats from DexScreener"""
        chain_id = chain_id or os.getenv('TOKEN_CHAIN')
        token_address = token_address or os.getenv('TOKEN_ADDRESS')

        if not token_address or not chain_id:
            logger.info("No token configuration found - skipping token stats")
            return False
        
        try:
            token_data = get_token_data(chain_id, token_address)
            if not token_data:
                return False
            
            formatted_stats = format_token_stats(token_data)
            print(formatted_stats)

            metadata = {
                "platform": "dexscreener",
                "chain": chain_id,
                "timestamp": datetime.now().isoformat(),
                "source": "token_stats",
                "content_type": "token_metrics"
            }

            memory_ids = self.memory_manager.create_chunks(
                category="metrics",
                direct_content=formatted_stats,
                content_type="metrics",
                metadata=metadata
            )
        
            return bool(memory_ids)
        
        except Exception as e:
            logger.error(f"Error updating token stats: {e}")
            return False

    def update_all_stats(self) -> bool:
        """Update stats from all platforms and clear old stats first"""
        # First try to delete existing stats
        if "metrics" in self.memory_manager.list_categories():
            if not self.memory_manager.remove_category("metrics"):
                logger.error("Failed to clear existing stats")
                return False

        platform_results = {
            'soundcloud': False,
            'youtube': False,
            'spotify': False,
            'dexscreener': False
        }

        # Uodate each platform
        if self.update_soundcloud_stats():
            platform_results['soundcloud'] = True
        if self.update_youtube_stats():
            platform_results['youtube'] = True
        if self.update_spotify_stats():
            platform_results['spotify'] = True
        if self.update_token_stats():
            platform_results['dexscreener'] = True
        
        # Summarize results
        successful = [platform for platform, result in platform_results.items() if result]
        failed = [platform for platform, result in platform_results.items() if not result]

        if successful:
            logger.info(f"Successfully updated stats for: {', '.join(successful)}")
        if failed:
            logger.info(f"Failed to update stats for: {', '.join(failed)}")

        # Return True if any platform succeeded
        return bool(successful)

    # TODO: Keep for potential search optimization. Adding common question patterns
    # to the stored text might improve semantic search results by providing more
    # context about how users ask about stats. Currently getting good results
    # without this but may be useful for fine-tuning later.
    def add_query_pattern(self, stats_text: str, platform: str) -> str: 
        "Add common query patterns to stats to improve retrieval"
        common_queries = [
            "How are your songs doing?",
            "How are your track performing?",
            "What are your streaming stats?",
            "What's your most played song?",
            f"How are your songs doing on {platform}?",
            "How many streams do you have?"
        ]

        # Extract song titles from the stats to add song-specific queries
        song_titles = self._extract_song_titles(stats_text)
        for title in song_titles:
            common_queries.extend([
                f"How is {title} performing?"
                f"How many plays does {title} have?",
                f"What are the stats for {title}?"
            ])
        
        header = "Common questions about these tracks"
        header += "\n".join(common_queries)
        
        return f"{header}\n\n{stats_text}"
    
    # Helper method for add_query_pattern(). May be used for generating
    # song-specific query patterns if we need to fine-tune search results
    def _extract_song_titles(self, stats_text: str) -> list[str]:
        """Extract song titles from formatted stats text"""
        titles = []
        lines = stats_text.split('\n')
        for line in lines:
            if line.startswith('Title: '):
                title = line.replace('Title: ', '').strip()
                titles.append(title)
        return titles
                               
                        
