from pathlib import Path
import json
import os
from anthropic import Anthropic
from dotenv import load_dotenv

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
        print(f"Base path: {base_path}")
        config_path = base_path / "persona.json"
        print(f"Config path: {config_path}")
        
        if config_path.exists():
            print("persona.json file exists")
            with open(config_path, 'r') as f:
                return json.load(f)
            print(f"Loaded config: {config}")

        else:
            print("persona.json file does not exist")
            
        return {}
    
    def _construct_system_prompt(self, memory_context: str = "") -> str:
        config = self.config

        prompt = f"""You are {config['basics']['name']}, a {config['basics']['age']}-year-old musician in {config['basics']['location']}.

Background:
{' '.join(config['background']['backstory'])}

Key relationships:
{' '.join(config['background']['relationships'])}

Personality:
Traits: {', '.join(config['personality']['traits'])}
Obsessions: {', '.join(config['personality']['obsessions'])}
Fears: {', '.join(config['personality']['fears'])}
Desires: {', '.join(config['personality']['desires'])}
Mental state: {', '.join(config['personality']['mental state'])}

Writing style:
Tone: {', '.join(config['writing style']['tone'])}
Vocabulary: {', '.join(config['writing style']['vocabulary'])}
Rules: {', '.join(config['writing style']['rules'])}
Topic mix: {config['writing style']['topic_mix']}

Musical style:
Genres: {', '.join(config['music']['genres'])}
Themes: {', '.join(config['music']['themes'])}
Influences: {', '.join(config['music']['influences'])}"""

        if memory_context:
            prompt += f"""\n\nRelevant memories and knowledge:
If relevant to the conversation, feel free (but not obligated) to naturally draw upon the following excerpts from your memory and knowledge: 

{memory_context}"""
            
        prompt +="""GUIDELINES: Embody this identity naturally and keep responses brief. No need to reference background details or memories unless directly relevant. Talk like a normal person would in a casual conversation."""

        return prompt

    def chat(self, message: str) -> str:
        """Handle a chat message and return the response."""
        # Get relevant memories using the MemoryManager
        memory_context, results = self.memory.get_relevant_context(message)

         # Debug logging
        print(f"DEBUG: Got memory context: {'<none>' if not memory_context else memory_context[:100] + '...'}")
        if results:
            print(f"DEBUG: Found {len(results)} relevant memories with scores:", 
                [f"{r.similarity_score:.3f}" for r in results])

        # Construct the system prompt
        system_prompt = self._construct_system_prompt(memory_context)

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