from pathlib import Path
import json
import os
from anthropic import Anthropic
from dotenv import load_dotenv
from datetime import datetime

from maistro.core.memory.manager import MemoryManager
from maistro.core.memory.types import SearchResult

class MusicAgent:
    def __init__(self, artist_name: str):
        # Load environment variables
        load_dotenv()

        # Initialize Anthropic client
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Load artist configurations
        self.artist_name = artist_name
        self.config = self._load_artist_config()

        # Initialize document memory
        self.memory = MemoryManager(artist_name)

        # Initialize conversation memory
        self.conversation_history = []
    
    def _load_artist_config(self) -> dict:
        base_path = Path(__file__).resolve().parent.parent / "artists" / self.artist_name.lower()
        config_path = base_path / "persona.json"
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
            
        return {}