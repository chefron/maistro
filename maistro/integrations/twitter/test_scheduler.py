#!/usr/bin/env python3
"""
Test script for the Twitter scheduler.
This script logs in to Twitter and schedules tweets at randomized intervals.

Usage:
    python test_scheduler.py [--2fa SECRET]

Options:
    --2fa SECRET: Two-factor authentication secret (optional)

The script reads Twitter credentials from the .env file in the project root.
Required environment variables:
    TWITTER_USERNAME: Twitter username or email
    TWITTER_PASSWORD: Twitter password
    TWITTER_EMAIL: Email for verification (optional)
    TWEET_MIN_INTERVAL: Minimum time between tweets in minutes (default: 30)
    TWEET_MAX_INTERVAL: Maximum time between tweets in minutes (default: 120)
"""

import sys
import os
import argparse
from dotenv import load_dotenv
import random
import time

# Import from our project modules
from auth import TwitterAuth
from post import TwitterPost
from scheduler import schedule_tweets, _get_interval_settings

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description='Test Twitter scheduler functionality')
    parser.add_argument('--2fa', dest='two_factor_secret', help='Two-factor authentication secret')
    args = parser.parse_args()
    
    # Get credentials from environment variables
    username = os.getenv('TWITTER_USERNAME')
    password = os.getenv('TWITTER_PASSWORD')
    email = os.getenv('TWITTER_EMAIL')
    two_factor_secret = args.two_factor_secret
    
    if not username or not password:
        print("Error: TWITTER_USERNAME and TWITTER_PASSWORD must be set in the .env file")
        sys.exit(1)
    
    # Get scheduler settings
    settings = _get_interval_settings()
    
    print("=== Twitter Scheduler Test ===")
    print(f"Username: {username}")
    print(f"Email provided: {'Yes' if email else 'No'}")
    print(f"2FA secret provided: {'Yes' if two_factor_secret else 'No'}")
    print(f"Tweet interval: {settings['min_interval']} to {settings['max_interval']} minutes")
    
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
    print("\nStarting scheduler to post tweets at randomized intervals...")
    print("Press Ctrl+C to stop the scheduler")
    
    # Start the scheduler using TwitterPost's generate_random_tweet method
    schedule_tweets(
        auth=auth,
        content_generator=TwitterPost.generate_random_tweet
    )
    
    print("\nScheduler stopped.")
    sys.exit(0)

if __name__ == "__main__":
    main()