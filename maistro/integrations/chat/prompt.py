from typing import Dict, Any, Optional, Tuple
from anthropic import Anthropic
from maistro.core.persona.generator import generate_character_prompt

def create_chat_prompt(
    config: Dict[str, Any], 
    artist_name: str,
    client: Optional[Anthropic] = None
) -> Tuple[str, Optional[str]]:
    """
    Create a prompt for interactive chat by generating a character prompt
    and adding chat-specific instructions if needed
    
    Args:
        config: Dictionary containing the artist persona configuration
        artist_name: Name of the artist
        client: Optional Anthropic client instance
        
    Returns:
        Tuple of (complete prompt string, path to saved prompt file or None)
    """
    # Generate the base character prompt
    character_prompt, prompt_path = generate_character_prompt(
        config=config,
        artist_name=artist_name,
        client=client
    )
    
    # Add chat-specific instructions
    chat_instructions = "\n\nCURRENT TASK: You're chatting with a user. Don't reference background details or memories unless directly relevant. Talk like a normal person would in a casual conversation. Be CONCISE. ALWAYS ensure you're following the rules before replying."
    complete_prompt = character_prompt + chat_instructions
    
    return complete_prompt, prompt_path