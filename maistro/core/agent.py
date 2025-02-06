from pathlib import Path
import json
import os
from anthropic import Anthropic
from dotenv import load_dotenv

class MusicAgent:
    def __init__(self, artist_name: str):
        # Load environment variables
        load_dotenv()

        # Initialize Anthropic client
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Load artist configurations
        self.artist_name = artist_name
        self.config = self._load_artist_config()

        # Initialize conversation memory
        self.conversation_history = []
    
    def _load_artist_config(self) -> dict:
        """Load all configuration files for the artist."""
        base_path = Path(__file__).parent.parent / "artists" / self.artist_name.lower()

        config = {}
        for file_name in ["core.json", "discography.json", "musical.json"]:
            file_path = base_path / file_name
            if file_path.exists():
                with open(file_path, 'r') as f:
                    config[file_name.replace('.json', '')] = json.load(f)

        return config
    
    def chat(self, message: str) -> str:
        """Handle a chat message and return the response."""
        # Construct the system prompt
        system_prompt = self._construct_system_prompt()

        # Add user message to history
        self.conversation_history.append({"role": "user", "content": message})

        # Get response from Claude
        response = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            system=system_prompt,
            messages=self.conversation_history,
        )

        # Add Claude's response to history
        self.conversation_history.append({"role": "assistant", "content": response.content[0].text})

        return response.content[0].text
    
    def _construct_system_prompt(self) -> str:
        """Construct the system prompt based on artist configuration"""
        core_config = self.config.get('core', {})

        prompt = f"""You are {core_config.get('identity', {}).get('name', 'an AI musician')}.

Bio and Background:
{' '.join(core_config.get('bio', []))}

Personal History:
{' '.join(core_config.get('lore', []))}

Your knowledge and expertise includes:
{' '.join(core_config.get('knowledge', []))}

Style notes:
{' '.join(core_config.get('style', {}).get('all', []))}
{' '.join(core_config.get('style', {}).get('chat', []))}

You maintain this personality consistently while engaging in natural conversation about music, the creative process, and life in general.
"""

        return prompt