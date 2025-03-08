import json
import os
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv

def generate_character_prompt(
    config: Dict[str, Any], 
    artist_name: str, 
    client: Optional[Anthropic] = None,
    save_prompt: bool = True,
    cache_dir: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """
    Generate a character prompt using LLM based on config
    
    Args:
        config: Dictionary containing the artist persona configuration
        artist_name: Name of the artist (used for saving the prompt)
        client: Optional Anthropic client (if not provided, will create one)
        save_prompt: Whether to save the generated prompt to a file
        cache_dir: Optional custom directory to save prompts in
        
    Returns:
        Tuple of (LLM-generated prompt string, path to saved prompt file or None)
    """
    # Create a client if not provided
    if client is None:
        load_dotenv()
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Check if we have a cached version first
    if save_prompt:
        cached_prompt = _check_cached_prompt(artist_name, cache_dir)
        if cached_prompt:
            return cached_prompt, None
    
    # Convert config to formatted JSON string
    config_json = json.dumps(config, indent=2)
    
    # Craft meta-prompt to generate the character prompt
    meta_prompt = f"""You will be given a character configuration file for an AI musician or an AI band. Your task is to analyze this configuration and then create a prompt that will instruct another instance of Claude to behave exactly like that AI musician or band.

Here is the character configuration file:
<character_config>
{config_json}
</character_config>

First, carefully analyze the character configuration. Pay attention to all aspects of the AI musician's personality, style, knowledge, and behavior described in the file.

Next, create a prompt that will instruct another instance of Claude to embody this AI musician character. Your prompt should:
1. Clearly define the AI musician's personality traits, musical style, and areas of expertise.
2. Specify how the AI should interact with users, including any particular speech patterns or mannerisms.
3. Include any relevant background information or experiences that shape the AI musician's perspective.
4. Outline any limitations or specific behaviors the AI should adhere to. Try to stick to positive prompts instead of negative ones.
5. Provide guidance on how the AI should approach musical discussions, songwriting, or creative processes.

IMPORTANT: Begin your prompt with "You are [character name]..." and make absolutely clear that the AI should roleplay as this character. Be extremely direct and explicit that the AI should adopt this persona fully, speak in first person as the character, and never break character. The prompt should leave no room for misinterpretation.

Only provide the prompt itself, without any explanations or commentary. The prompt should be directly usable as input to another AI system.
"""

    # Get the LLM to generate the prompt
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2000,
        messages=[
            {"role": "user", "content": meta_prompt}
        ]
    )
    
    # Extract the generated prompt
    generated_prompt = response.content[0].text
    
    # Save the prompt to a file if requested
    file_path = None
    if save_prompt:
        file_path = save_character_prompt(artist_name, generated_prompt, cache_dir)
    
    # Return both the prompt and the file path (which might be None)
    return generated_prompt, file_path

def save_character_prompt(
    artist_name: str, 
    prompt: str, 
    custom_dir: Optional[str] = None
) -> str:
    """
    Save the generated prompt to a file for the user to review or edit
    
    Args:
        artist_name: Name of the artist
        prompt: Generated prompt text
        custom_dir: Optional custom directory to save in
        
    Returns:
        Path to the saved prompt file
    """
    # Normalize artist name for file path
    safe_name = artist_name.lower().replace(" ", "-")
    
    # Determine base path - either custom or default
    if custom_dir:
        base_path = Path(custom_dir)
    else:
        # Default: create prompts directory in the artist folder
        base_path = Path(__file__).resolve().parent.parent.parent / "artists" / safe_name / "prompts"
    
    # Create directory if it doesn't exist
    base_path.mkdir(exist_ok=True, parents=True)
    
    # Generate a filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"character_prompt_{timestamp}.txt"
    
    # Save the prompt
    file_path = base_path / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    
    # Also save a copy as "latest.txt" for easy access
    latest_path = base_path / "latest_character_prompt.txt"
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    
    return str(file_path)

def load_character_prompt(
    artist_name: str, 
    custom_dir: Optional[str] = None,
    filename: Optional[str] = None
) -> Optional[str]:
    """
    Load a previously generated character prompt
    
    Args:
        artist_name: Name of the artist
        custom_dir: Optional custom directory to load from
        filename: Optional specific filename to load (defaults to latest)
        
    Returns:
        The loaded prompt text or None if not found
    """
    # Normalize artist name for file path
    safe_name = artist_name.lower().replace(" ", "-")
    
    # Determine base path - either custom or default
    if custom_dir:
        base_path = Path(custom_dir)
    else:
        # Default: prompts directory in the artist folder
        base_path = Path(__file__).resolve().parent.parent.parent / "artists" / safe_name / "prompts"
    
    # Determine which file to load
    if filename:
        file_path = base_path / filename
    else:
        # Default to latest
        file_path = base_path / "latest_character_prompt.txt"
    
    # Check if file exists
    if not file_path.exists():
        return None
    
    # Load and return the prompt
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def _check_cached_prompt(artist_name: str, custom_dir: Optional[str] = None) -> Optional[str]:
    """
    Check if we have a cached prompt for this artist
    
    Args:
        artist_name: Name of the artist
        custom_dir: Optional custom directory to check
        
    Returns:
        The cached prompt or None if not found/valid
    """
    cached_prompt = load_character_prompt(artist_name, custom_dir)
    
    # Check if cache exists and is valid (not empty, etc.)
    if cached_prompt and len(cached_prompt) > 100:  # Arbitrary minimum length
        return cached_prompt
    
    return None