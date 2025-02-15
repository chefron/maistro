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
        self.memory_manager.create(
            category="streaming_stats",
            content=formatted_stats,
            metadata={
                "platform": "soundcloud",
                "timestamp": datetime.now().isoformat()
            }
        )
        return True
        