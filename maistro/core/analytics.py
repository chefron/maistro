from datetime import datetime
from dotenv import load_dotenv
import os
from maistro.core.memory.manager import MemoryManager
from maistro.integrations.platforms.soundcloud.soundcloud import get_user_tracks_data, format_track_stats

load_dotenv()

class PlatformStats:
    """Handles gathering and storing platform-specific stats"""
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager

    def update_soundcloud_stats(self, user_id: str = None, client_id: str = None) -> bool:
        """Fetch, format, and store SoundCloud stats"""
        user_id = user_id or os.getenv('SOUNDCLOUD_USER_ID')
        client_id = client_id or os.getenv('SOUNDCLOUD_CLIENT_ID')
        
        tracks_info = get_user_tracks_data(user_id, client_id)
        if not tracks_info:
            return False
        
        formatted_stats = format_track_stats(tracks_info)
        print(formatted_stats)

        # remove existing stats
        self.memory_manager.remove_category("streaming_stats")

        metadata = {
            "platform": "soundcloud",
            "timestamp": datetime.now().isoformat(),
            "source": "soundcloud_stats",
            "content_type": "performance_metrics",
        }

        memory_ids = self.memory_manager.create_chunks(
            category="streaming_stats",
            direct_content=formatted_stats,
            content_type="analytics",
            metadata=metadata
        )
        
        return bool(memory_ids)
    
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
    
    def _extract_song_titles(self, stats_text: str) -> list[str]:
        """Extract song titles from formatted stats text"""
        titles = []
        lines = stats_text.split('\n')
        for line in lines:
            if line.startswith('Title: '):
                title = line.replace('Title: ', '').strip()
                titles.append(title)
        return titles
                               
                        
