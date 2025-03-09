#!/usr/bin/env python3
"""
Twitter API posting module for reliable tweeting via the official API.

This module provides posting functionality using the Twitter API v2
while allowing the rest of the system to use scraping for mentions monitoring.

To use:
1. Set up Twitter API credentials in .env file:
   TWITTER_API_KEY=your_api_key
   TWITTER_API_SECRET=your_api_secret
   TWITTER_ACCESS_TOKEN=your_access_token
   TWITTER_ACCESS_SECRET=your_access_secret

2. Create an APITwitterPost instance, which has the same interface as the
   scraper-based TwitterPost for easy integration.
"""

import os
import random
import time
import logging
from typing import Dict, List, Optional
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv

# Import from our project modules for compatibility
from utils import TwitterError
from maistro.core.persona.generator import generate_character_prompt

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('twitter_api_post')

class APITwitterPost:
    """Handles posting tweets using the official Twitter API v2"""
    
    # API endpoints
    CREATE_TWEET_URL = "https://api.twitter.com/2/tweets"
    
    def __init__(self, auth=None):
        """
        Initialize with Twitter API credentials from environment variables.
        
        The auth parameter is accepted for compatibility with the existing
        TwitterPost class but is not used for API requests.
        
        Args:
            auth: Optional placeholder for compatibility with TwitterPost
        """
        # Store the auth object for compatibility
        self.auth = auth
        
        # Get API credentials from environment variables
        self.api_key = os.getenv('TWITTER_API_KEY')
        self.api_secret = os.getenv('TWITTER_API_SECRET')
        self.access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.access_secret = os.getenv('TWITTER_ACCESS_SECRET')
        
        # Check if credentials are provided
        if not all([self.api_key, self.api_secret, self.access_token, self.access_secret]):
            raise TwitterError(
                "Twitter API credentials not found. Please set TWITTER_API_KEY, "
                "TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, and TWITTER_ACCESS_SECRET "
                "in your .env file."
            )
        
        # Set up OAuth1 authentication
        self.oauth = OAuth1(
            self.api_key,
            client_secret=self.api_secret,
            resource_owner_key=self.access_token,
            resource_owner_secret=self.access_secret
        )
        
        # Extract username from auth object if available (for compatibility)
        self.username = getattr(auth, 'username', None)
        
        logger.info(f"Initialized APITwitterPost for user: {self.username or 'Unknown'}")
    
    def create_tweet(self, text: str, reply_to_id: Optional[str] = None) -> Dict:
        """
        Create a new tweet using Twitter API v2.
        
        Args:
            text: The text content of the tweet
            reply_to_id: Optional tweet ID to reply to
                
        Returns:
            Dict: Response from Twitter API
        """
        # Optional: Simulate natural behavior for consistency with the scraper approach
        self._simulate_natural_behavior()
        
        logger.info(f"Creating tweet: {text}")
        
        # Prepare the request payload
        payload = {"text": text}
        
        # Add reply information if provided
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}
        
        try:
            # Make the API request
            response = requests.post(
                self.CREATE_TWEET_URL,
                json=payload,
                auth=self.oauth,
                headers={
                    'Content-Type': 'application/json',
                }
            )
            
            # Check for successful response
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Successfully created tweet with ID: {result.get('data', {}).get('id')}")
            
            # Optional: Add a small delay after posting (mimics natural behavior)
            time.sleep(random.uniform(1.0, 3.0))
            
            return result
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to create tweet: {e}"
            
            # Try to extract more detailed error information
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = f"Twitter API error: {error_data.get('title', 'Unknown error')} - {error_data.get('detail', '')}"
                except ValueError:
                    pass
            
            logger.error(error_msg)
            raise TwitterError(error_msg)
    
    def _simulate_natural_behavior(self):
        """
        Simulate natural user behavior before posting.
        
        This is optional but helps maintain consistency with the scraper approach.
        """
        # Simulate thinking time
        thinking_time = random.uniform(2.0, 5.0)
        logger.info(f"Simulating pre-tweet delay of {thinking_time:.2f} seconds...")
        time.sleep(thinking_time)
    
    def generate_tweet(self, agent, max_length=280):
        """Generate a tweet using the agent"""
        
        # Get the Twitter username from the current auth object
        twitter_username = self.username or "user" # Fallback if username is not available
        
        # Create a Twitter-specific prompt using the character generator
        # First get the base character prompt
        character_prompt, _ = generate_character_prompt(
            config=agent.config,
            artist_name=agent.artist_name,
            client=agent.client
        )
        
        # Add Twitter-specific instructions
        twitter_instructions = f"""

CURRENT TASK: You're composing a tweet for Twitter. As {agent.artist_name}, write a single, authentic statement that reflects your personality and musical identity.

- Post as if you were tweeting from the @{twitter_username} account.
- Keep it brief and concise (maximum {max_length} characters).
- Avoid asking questions - make statements instead.
- Be authentic to your character voice and musical style.
- Don't add commentary or acknowledge this as a request.
- Don't use hashtags unless they're genuinely part of your natural voice.

Just write the tweet text itself with no additional explanation."""
        
        complete_prompt = character_prompt + twitter_instructions
        
        # Debug output - print the entire prompt being sent to the LLM
        print("\n========== PROMPT SENT TO LLM ==========")
        print(complete_prompt)
        print("========================================\n")
        
        # Use the combined prompt instead of system+user separation
        response = agent.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=150,  # Limit to a short response
            messages=[{"role": "user", "content": complete_prompt}]
        )
        
        tweet_content = response.content[0].text.strip()
        
        # Ensure tweet is within character limit
        if len(tweet_content) > max_length:
            tweet_content = tweet_content[:max_length-3] + "..."
            
        logger.info(f"Generated tweet: {tweet_content}")
        return tweet_content