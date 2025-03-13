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
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv

# Import from our project modules for compatibility
from .utils import TwitterError
from maistro.core.persona.generator import generate_character_prompt
from .conversation_tracker import ConversationTracker

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('twitter_api_post')

class TweetHistory:
    """Tracks tweet history to avoid repetition"""
    
    def __init__(self, cache_dir: str, username: str, max_history: int = 50):
        """
        Initialize the tweet history tracker
        
        Args:
            cache_dir: Directory to store tweet data
            username: Bot's Twitter username
            max_history: Maximum number of tweets to remember
        """
        self.cache_dir = cache_dir
        self.username = username
        self.max_history = max_history
        self.history_file = os.path.join(cache_dir, f"{username}_tweet_history.json")
        self.tweets = []
        self.logger = logging.getLogger('twitter_tweet_history')
        
        # Load existing history
        self._load_history()
    
    def _load_history(self):
        """Load tweet history from disk"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    self.tweets = json.load(f)
                self.logger.info(f"Loaded {len(self.tweets)} previous tweets")
            else:
                self.tweets = []
                self.logger.info("No existing tweet history found")
        except Exception as e:
            self.logger.error(f"Error loading tweet history: {e}")
            self.tweets = []
    
    def _save_history(self):
        """Save tweet history to disk"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.tweets, f, indent=2)
            self.logger.info(f"Saved {len(self.tweets)} tweets to history")
        except Exception as e:
            self.logger.error(f"Error saving tweet history: {e}")
    
    def add_tweet(self, text: str, tweet_id: str = None):
        """
        Add a new tweet to the history
        
        Args:
            text: The text of the tweet
            tweet_id: Optional ID of the tweet
        """
        # Create a record of the tweet
        tweet_record = {
            "text": text,
            "id": tweet_id or str(hash(text)),
            "timestamp": datetime.now().isoformat()
        }
        
        # Add to the beginning of the list
        self.tweets.insert(0, tweet_record)
        
        # Limit history size
        if len(self.tweets) > self.max_history:
            self.tweets = self.tweets[:self.max_history]
        
        # Save updated history
        self._save_history()
    
    def get_recent_tweets(self, count: int = 10) -> list:
        """
        Get most recent tweets
        
        Args:
            count: Number of tweets to retrieve
            
        Returns:
            List of recent tweet texts
        """
        return [tweet["text"] for tweet in self.tweets[:count]]
    
    def is_too_similar(self, text: str, threshold: float = 0.7) -> bool:
        """
        Check if a tweet is too similar to recent tweets
        
        Args:
            text: The text to check
            threshold: Similarity threshold (0.0 to 1.0)
            
        Returns:
            True if tweet is too similar to a recent tweet
        """
        # If no history, it can't be similar
        if not self.tweets:
            return False
        
        # Get recent tweets for comparison
        recent_tweets = self.get_recent_tweets(10)
        
        # Simple check for identical tweets
        if text in recent_tweets:
            return True
        
        # Check for high similarity
        return self._check_similarity(text, recent_tweets, threshold)
    
    def _check_similarity(self, text: str, previous_tweets: list, threshold: float) -> bool:
        """
        Perform similarity check on tweets
        
        Args:
            text: New tweet text
            previous_tweets: List of previous tweet texts
            threshold: Similarity threshold
            
        Returns:
            True if the new tweet is too similar to any previous tweet
        """
        # Simple word overlap coefficient calculation
        def word_overlap(a, b):
            # Convert to lowercase and split into words
            a_words = set(a.lower().split())
            b_words = set(b.lower().split())
            
            # Calculate overlap coefficient
            intersection = len(a_words.intersection(b_words))
            smaller_set = min(len(a_words), len(b_words))
            
            if smaller_set == 0:
                return 0.0
                
            return intersection / smaller_set
            
        # Check similarity with each previous tweet
        for prev_tweet in previous_tweets:
            similarity = word_overlap(text, prev_tweet)
            if similarity >= threshold:
                return True
                
        return False

class APITwitterPost:
    """Handles posting tweets using the official Twitter API v2"""
    
    # API endpoints
    CREATE_TWEET_URL = "https://api.twitter.com/2/tweets"
    
    # Define topic suggestions to encourage variety
    TOPIC_SUGGESTIONS = [
        "streaming stats",
        "creative process",
        "personal life",
        "AI music",
        "inspiration",
        "collaboration",
        "fan interaction",
        "philosophical thoughts",
        "music recommendations"
    ]
    
    def __init__(self, auth=None, conversation_tracker=None):
        """
        Initialize with Twitter API credentials from environment variables.
        
        The auth parameter is accepted for compatibility with the existing
        TwitterPost class but is not used for API requests.
        
        Args:
            auth: Optional placeholder for compatibility with TwitterPost
            conversation_tracker: Optional ConversationTracker instance
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
        
        # Create cache directory for tweet history
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Initialize tweet history tracker if username is available
        self.tweet_history = None
        if self.username:
            self.tweet_history = TweetHistory(self.cache_dir, self.username)

        self.conversation_tracker = conversation_tracker
        
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
            
            tweet_id = result.get('data', {}).get('id')
            logger.info(f"Successfully created tweet with ID: {tweet_id}")
            
            # Add tweet to history if we're tracking it
            if self.tweet_history and not reply_to_id:  # Only track original tweets, not replies
                self.tweet_history.add_tweet(text, tweet_id)

            # Also store in conversation tracker if available
            if hasattr(self, 'conversation_tracker') and self.conversation_tracker and not reply_to_id and tweet_id:
                self.conversation_tracker.store_original_tweet(tweet_id, text)
            else:
                print(f"DIAGNOSTIC: NOT storing tweet. has tracker: {hasattr(self, 'conversation_tracker')}, tracker is: {self.conversation_tracker}, is reply: {bool(reply_to_id)}, tweet_id: {tweet_id}")
            
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
    
    def generate_tweet(self, agent, max_length=280, max_attempts=3):
        """Generate a tweet using the agent with memory integration and variety enforcement"""
        
        # Get the Twitter username from the current auth object
        twitter_username = self.username or "user" # Fallback if username is not available
        
        # Select a single topic instead of multiple
        topic = random.choice(self.TOPIC_SUGGESTIONS)
        
        # Query agent's memory for relevant context related to the topic
        memory_context = ""
        try:
            memory_context, results = agent.memory.get_relevant_context(
                query=topic,
                n_results=3  # Just get the top 3 most relevant memories
            )
        except Exception as e:
            logger.error(f"Error retrieving memory context: {e}")
        
        # Get recent tweets for context if available
        recent_tweets = []
        if self.tweet_history:
            recent_tweets = self.tweet_history.get_recent_tweets(5)
        
        # Create a Twitter-specific prompt using the character generator
        character_prompt, _ = generate_character_prompt(
            config=agent.config,
            artist_name=agent.artist_name,
            client=agent.client
        )
        
        # Add Twitter-specific instructions with clean structure
        twitter_instructions = f"""

    === TWEET CREATION TASK ===

    You're composing a tweet for Twitter. Please write a single authentic statement that reflects your personality and musical identity.

    - Post as if you were tweeting from the @{twitter_username} account.
    - Keep it brief and concise (maximum {max_length} characters).
    - Don't fabricate streaming stats!
    - Don't use hashtags unless they're genuinely part of your natural voice.

    === TWEET TOPIC ===

    I want you to tweet about: {topic}
    """

        # Add memory context if available, directly connected to the topic
        if memory_context:
            twitter_instructions += f"""

    === RELEVANT MEMORIES ===

    If directly relevant to this topic, feel free (but not obligated) to naturally draw upon the following excerpts from your memory and knowledge:

    {memory_context}
    """
        else:
            twitter_instructions += """

    === RELEVANT MEMORIES ===

    No specific memories found related to this topic - tweet from your general perspective.
    """

        # Add variety instructions in a cleaner way
        if recent_tweets:
            twitter_instructions += f"""

    === VARIETY GUIDELINES ===

    For variety, please avoid being similar to your recent tweets:
    """
            for i, tweet in enumerate(recent_tweets):
                twitter_instructions += f"- \"{tweet}\"\n"
        
        twitter_instructions += """

    === OUTPUT INSTRUCTIONS ===

    Just write the tweet text itself with no additional explanation.
    """
        
        complete_prompt = character_prompt + twitter_instructions
        
        # Debug output
        print("\n========== PROMPT SENT TO LLM ==========")
        print(complete_prompt)
        print("========================================\n")
        
        # Make attempts with simplified retry logic
        for attempt in range(max_attempts):
            response = agent.client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=1000,
                messages=[{"role": "user", "content": complete_prompt}]
            )
            
            tweet_content = response.content[0].text.strip()
            
            # Ensure tweet is within character limit
            if len(tweet_content) > max_length:
                tweet_content = tweet_content[:max_length-3] + "..."
            
            # Check if tweet is too similar to recent ones
            if self.tweet_history and self.tweet_history.is_too_similar(tweet_content):
                if attempt == max_attempts - 1:
                    break  # Use it anyway on last attempt
                    
                # Simpler retry instruction
                complete_prompt += "\n\nPlease try again with a more distinct and original tweet."
                continue
                
            break
                
        logger.info(f"Generated tweet: {tweet_content}")
        return tweet_content