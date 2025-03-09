#!/usr/bin/env python3
"""
Test script for Twitter bot with tweet scheduling, mentions handling, and MusicAgent integration.
This script logs in to Twitter, schedules AI-generated tweets at randomized intervals,
and responds to mentions using the MusicAgent persona.

Usage:
    python test_with_mentions.py [--2fa SECRET] [--no-tweets] [--no-mentions] [--artist ARTIST_NAME]

Options:
    --2fa SECRET: Two-factor authentication secret (optional)
    --no-tweets: Disable tweet scheduling
    --no-mentions: Disable mentions checking
    --artist ARTIST_NAME: Name of the artist to use (default: "dolla-llama")

The script reads Twitter credentials from the .env file in the project root.
Required environment variables:
    TWITTER_USERNAME: Twitter username or email
    TWITTER_PASSWORD: Twitter password
    TWITTER_EMAIL: Email for verification (optional)
    TWEET_MIN_INTERVAL: Minimum time between tweets in minutes (default: 30)
    TWEET_MAX_INTERVAL: Maximum time between tweets in minutes (default: 120)
    MENTION_CHECK_INTERVAL: Time between mention checks in seconds (default: 120)
    ANTHROPIC_API_KEY: API key for Anthropic Claude (required for MusicAgent)
"""

import sys
import os
import argparse
from dotenv import load_dotenv
import random
import time
import threading
import signal

# Import from our project modules
from auth import TwitterAuth
from scheduler import schedule_tweets, start_scheduler, stop_scheduler, _get_interval_settings
from mentions import start_mentions_checker, stop_mentions_checker, MentionsHandler
from api_post import APITwitterPost

# Import MusicAgent for AI-powered content
from maistro.core.agent import MusicAgent

# Load environment variables
load_dotenv()

def generate_tweet_with_agent(agent):
    """Generate a tweet using the MusicAgent"""
    try:
        # Use the APITwitterPost to generate a tweet with the agent
        poster = APITwitterPost(auth=global_auth)
        tweet_text = poster.generate_tweet(agent)
        print(f"Generated tweet: {tweet_text}")
        return tweet_text
    except Exception as e:
        print(f"Error generating tweet: {e}")
        # Fallback to a simple tweet if generation fails
        return "Just thinking about music today... #musicthoughts"

def ai_respond_to_mention(mention, agent):
    """Generate a response to a mention using the MusicAgent"""
    try:
        # Format the mention as a prompt for the agent
        prompt = f"Someone on Twitter with the username @{mention['username']} said: {mention['text']}\n\nPlease craft a friendly reply as yourself (max 250 characters). Don't add any explanations or format it as a tweet, just write the reply content."
        
        # Get the existing system prompt that already has the persona details
        system_prompt = agent._construct_system_prompt()
        
        # Get response directly from Claude (similar to how agent.chat() works)
        response = agent.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=250,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )
        
        reply_text = response.content[0].text.strip()
        
        # Ensure reply is within Twitter's character limit
        if len(reply_text) > 280:
            reply_text = reply_text[:277] + "..."
            
        print(f"AI generated reply: {reply_text}")
        return reply_text
    except Exception as e:
        print(f"Error generating AI response: {e}")
        # Fallback to a simple response if generation fails
        return f"Thanks for reaching out @{mention['username']}! Appreciate you connecting with me."

# Global variables to maintain state
global_auth = None
global_agent = None

def main():
    parser = argparse.ArgumentParser(description='Test Twitter bot with scheduling and mentions')
    parser.add_argument('--2fa', dest='two_factor_secret', help='Two-factor authentication secret')
    parser.add_argument('--no-tweets', action='store_true', help='Disable tweet scheduling')
    parser.add_argument('--no-mentions', action='store_true', help='Disable mentions checking')
    parser.add_argument('--artist', dest='artist_name', default='dolla-llama', help='Name of the artist to use')
    args = parser.parse_args()
    
    global global_auth, global_agent
    
    # Get credentials from environment variables
    username = os.getenv('TWITTER_USERNAME')
    password = os.getenv('TWITTER_PASSWORD')
    email = os.getenv('TWITTER_EMAIL')
    two_factor_secret = args.two_factor_secret
    
    if not username or not password:
        print("Error: TWITTER_USERNAME and TWITTER_PASSWORD must be set in the .env file")
        sys.exit(1)
    
    # Verify Anthropic API key is available
    if not os.getenv('ANTHROPIC_API_KEY'):
        print("Error: ANTHROPIC_API_KEY must be set in the .env file")
        sys.exit(1)
        
    # Get settings
    tweet_settings = _get_interval_settings()
    mention_interval_minutes = int(os.getenv('MENTION_CHECK_INTERVAL', '5'))  # Default 5 minutes
    mention_interval = mention_interval_minutes * 60  # Convert to seconds for internal use
    
    print("=== Twitter Bot Test ===")
    print(f"Username: {username}")
    print(f"Email provided: {'Yes' if email else 'No'}")
    print(f"2FA secret provided: {'Yes' if two_factor_secret else 'No'}")
    print(f"Artist: {args.artist_name}")
    
    if not args.no_tweets:
        print(f"Tweet interval: {tweet_settings['min_interval']} to {tweet_settings['max_interval']} minutes")
    else:
        print("Tweet scheduling disabled")
        
    if not args.no_mentions:
        print(f"Mention check interval: {mention_interval_minutes} minutes")
    else:
        print("Mentions checking disabled")
    
    # Initialize MusicAgent
    print("\nInitializing MusicAgent...")
    try:
        global_agent = MusicAgent(args.artist_name)
        print(f"✅ Successfully initialized {args.artist_name} agent")
    except Exception as e:
        print(f"Failed to initialize MusicAgent: {e}")
        sys.exit(1)
    
    # Initialize Twitter authentication
    print("\nInitializing Twitter auth...")
    auth = TwitterAuth()
    global_auth = auth
    
    # Login with retry
    print("\nAttempting to login...")
    login_success = auth.login_with_retry(username, password, email, two_factor_secret)
    
    if not login_success:
        print("Failed to log in to Twitter. Exiting.")
        sys.exit(1)
    
    print("\n✅ Successfully logged in to Twitter")
    
    # Register signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        print(f"\nReceived signal {sig}. Shutting down...")
        
        # Stop schedulers
        if not args.no_tweets:
            stop_scheduler()
        if not args.no_mentions:
            stop_mentions_checker()
            
        print("Shutdown complete.")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create a custom tweet generator that uses the MusicAgent
    def custom_tweet_generator():
        return generate_tweet_with_agent(global_agent)
    
    # Create a custom mention handler that uses the MusicAgent
    def custom_mention_handler(mention):
        reply_text = ai_respond_to_mention(mention, global_agent)
        # Use APITwitterPost to post the reply
        poster = APITwitterPost(auth=auth)
        return poster.create_tweet(reply_text, reply_to_id=mention['id'])
    
    # Start tweet scheduler if enabled
    if not args.no_tweets:
        print("\nStarting scheduler to post AI-generated tweets at randomized intervals...")
        start_scheduler(
            auth=auth,
            content_generator=custom_tweet_generator
        )
    
    # Start mentions checker if enabled
    if not args.no_mentions:
        print(f"\nStarting mentions checker (checking every {mention_interval} seconds)...")
        
        # Patch the MentionsHandler to use our custom AI response function
        original_process_mention = MentionsHandler.process_mention
        
        def patched_process_mention(self, mention):
            try:
                mention_id = mention["id"]
                username = mention["username"]
                
                print(f"Processing mention {mention_id} from @{username}")
                
                # Generate AI response
                reply = ai_respond_to_mention(mention, global_agent)
                
                # Post the reply
                print(f"Replying to tweet {mention_id}: {reply}")
                result = self.poster.create_tweet(reply, mention_id)
                
                # Update last checked ID if this ID is newer
                if not self.last_checked_id or mention_id > self.last_checked_id:
                    self._save_last_checked_id(mention_id)
                    
                print(f"Successfully replied to mention {mention_id}")
                return True
                
            except Exception as e:
                print(f"Error processing mention: {e}")
                return False
        
        # Apply the patch
        MentionsHandler.process_mention = patched_process_mention
        
        start_mentions_checker(
            auth=auth,
            interval=mention_interval
        )
    
    print("\nBot is running. Press Ctrl+C to stop.")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    
    sys.exit(0)

if __name__ == "__main__":
    main()