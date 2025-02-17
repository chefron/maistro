from datetime import datetime
from dotenv import load_dotenv
import os
from maistro.core.memory.manager import MemoryManager
from maistro.integrations.platforms.soundcloud.soundcloud import get_user_tracks_data, format_track_stats
from maistro.integrations.platforms.youtube.youtube import get_youtube_channel_stats, get_channel_videos, format_video_stats

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
                category="streaming_stats",
                direct_content=formatted_stats,
                content_type="analysis",
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
            # Get channel and video data
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
                category="streaming_stats",
                direct_content=formatted_stats,
                content_type="analysis",
                metadata=metadata
            )
            
            return bool(memory_ids)
        
        except Exception as e:
            logger.error(f"Error updating YouTube stats: {e}")
            return False
        
    def update_all_stats(self) -> bool:
        """Update stats from all platforms and clear old stats first"""
        # Clear existing stats before updating
        self.memory_manager.remove_category("streaming_stats")

        # Update all platforms
        success = False

        if not self.update_soundcloud_stats():
            logger.error("Failed to update SoundCloud stats")
        else:
            success = True
            
        if not self.update_youtube_stats():
            logger.error("Failed to update YouTube stats")
        else:
            success = True
            
        return success

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
                               
                        
