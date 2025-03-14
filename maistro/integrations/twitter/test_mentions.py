#!/usr/bin/env python3
"""
Test script for Twitter bot with tweet scheduling and mentions handling.
This script logs in to Twitter, schedules tweets at randomized intervals,
and responds to mentions using the MusicAgent for AI-generated content.

Usage:
    python test_mentions.py [--2fa SECRET] [--no-tweets] [--no-mentions] [--artist ARTIST]

Options:
    --2fa SECRET: Two-factor authentication secret (optional)
    --no-tweets: Disable tweet scheduling
    --no-mentions: Disable mentions checking
    --artist ARTIST: Specify the artist name (default: dolla-llama)

The script reads Twitter credentials from the .env file in the project root.
Required environment variables:
    TWITTER_USERNAME: Twitter username or email
    TWITTER_PASSWORD: Twitter password
    TWITTER_EMAIL: Email for verification (optional)
    TWEET_MIN_INTERVAL: Minimum time between tweets in minutes (default: 30)
    TWEET_MAX_INTERVAL: Maximum time between tweets in minutes (default: 120)
    MENTION_CHECK_INTERVAL: Time between mention checks in seconds (default: 120)
    ANTHROPIC_API_KEY: API key for Claude
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
from mentions import start_mentions_checker, stop_mentions_checker
from api_post import APITwitterPost
from conversation_tracker import ConversationTracker

# Import MusicAgent for AI-generated content
from maistro.core.agent import MusicAgent

# Load environment variables
load_dotenv()

def main():
    parser = argparse.ArgumentParser(description='Test Twitter bot with scheduling and mentions')
    parser.add_argument('--2fa', dest='two_factor_secret', help='Two-factor authentication secret')
    parser.add_argument('--no-tweets', action='store_true', help='Disable tweet scheduling')
    parser.add_argument('--no-mentions', action='store_true', help='Disable mentions checking')
    parser.add_argument('--artist', dest='artist_name', default='dolla-llama', help='Artist name to use (default: dolla-llama)')
    args = parser.parse_args()
    
    # Get credentials from environment variables
    username = os.getenv('TWITTER_USERNAME')
    password = os.getenv('TWITTER_PASSWORD')
    email = os.getenv('TWITTER_EMAIL')
    two_factor_secret = args.two_factor_secret
    
    if not username or not password:
        print("Error: TWITTER_USERNAME and TWITTER_PASSWORD must be set in the .env file")
        sys.exit(1)
    
    # Check for Anthropic API key
    if not os.getenv('ANTHROPIC_API_KEY'):
        print("Error: ANTHROPIC_API_KEY must be set in the .env file for AI functionality")
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
        agent = MusicAgent(args.artist_name)
        print(f"✅ Successfully initialized {args.artist_name} agent")
    except Exception as e:
        print(f"Failed to initialize MusicAgent: {e}")
        sys.exit(1)
    
    # Initialize Twitter authentication
    print("\nInitializing Twitter auth...")
    auth = TwitterAuth()
    
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

    # Create a shared conversation tracker
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    conversation_tracker = ConversationTracker(cache_dir, auth.username)
    print(f"\nCreated shared conversation tracker for @{auth.username}")
    
    # Start tweet scheduler if enabled
    if not args.no_tweets:
        print("\nStarting scheduler to post AI-generated tweets at randomized intervals...")
        
        # Create a custom tweet generator that uses APITwitterPost with the agent
        def generate_tweet():
            try:
                # Create APITwitterPost with the shared conversation tracker
                api_poster = APITwitterPost(auth=auth, conversation_tracker=conversation_tracker)
                return api_poster.generate_tweet(agent)
            except Exception as e:
                print(f"Error generating tweet: {e}")
                return None
        
        start_scheduler(
            auth=auth,
            content_generator=generate_tweet
        )
    
    # Start mentions checker if enabled
    if not args.no_mentions:
        print(f"\nStarting mentions checker (checking every {mention_interval} seconds)...")
        
        # Pass the shared conversation tracker to start_mentions_checker
        # Note: This requires updating start_mentions_checker in mentions.py to accept this parameter
        start_mentions_checker(
            auth=auth,
            agent=agent,
            conversation_tracker=conversation_tracker,  # Pass the shared tracker
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