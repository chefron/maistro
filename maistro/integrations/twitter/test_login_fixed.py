#!/usr/bin/env python3
"""
Test script for the Twitter client login and posting functionality.
This script attempts to log in to Twitter with improved anti-detection measures and post a tweet.

Usage:
    python test_login.py [--2fa SECRET]

Options:
    --2fa SECRET: Two-factor authentication secret (optional)

The script reads Twitter credentials from the .env file in the project root.
Required environment variables:
    TWITTER_USERNAME: Twitter username or email
    TWITTER_PASSWORD: Twitter password
    TWITTER_EMAIL: Email for verification (optional)
"""

import sys
import os
import time
import random
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Import from our new modular structure
from auth import TwitterAuth
from post import TwitterPost
from utils import TwitterError

load_dotenv()

def test_login_and_post(username, password, email=None, two_factor_secret=None):
    """Test login and posting functionality with improved anti-detection measures"""
    print("\n=== Testing login functionality with improved timing ===")
    
    # Add a pre-login delay to appear more human-like
    human_delay = random.uniform(4.0, 7.0)
    print(f"Adding pre-login delay of {human_delay:.2f} seconds...")
    time.sleep(human_delay)
    
    # Create auth instance for login
    print("Initializing Twitter auth...")
    auth = TwitterAuth()
    
    # Modify timing parameters to avoid triggering Twitter's anti-bot detection
    auth.min_delay = 2.0  # Increase minimum delay between requests
    auth.max_delay = 5.0  # Increase maximum delay between requests
    
    # Try to login
    login_success = auth.login_with_retry(username, password, email, two_factor_secret)
    
    if login_success:
        print("✅ Successfully logged in to Twitter")
        
        # Test creating a tweet
        print("\n=== Testing tweet creation ===")
        try:
            # Create the poster instance with authenticated auth object
            poster = TwitterPost(auth)
            
            # Add a longer delay before attempting to tweet
            tweet_delay = random.uniform(5.0, 11.0)
            print(f"Adding pre-tweet delay of {tweet_delay:.2f} seconds...")
            time.sleep(tweet_delay)
            
            # Test tweet content
            tweet_text = "Just testing my Twitter client - " + time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Post the tweet
            result = poster.create_tweet(tweet_text)
            print(f"✅ Successfully created tweet: {result.get('data', {}).get('text', 'Unknown')}")
            
            return True
        except Exception as e:
            print(f"❌ Error creating tweet: {e}")
            return False
    else:
        print("❌ Failed to log in to Twitter")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test Twitter login and posting functionality')
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
    
    print("=== Twitter Login and Post Test ===")
    print(f"Username: {username}")
    print(f"Email provided: {'Yes' if email else 'No'}")
    print(f"2FA secret provided: {'Yes' if two_factor_secret else 'No'}")
    
    success = test_login_and_post(username, password, email, two_factor_secret)
    
    if success:
        print("\n✅ All tests passed! The login and posting functionality are working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Tests failed. There are issues with login or posting.")
        print("\nTroubleshooting tips:")
        print("1. Check if the account is locked by trying to log in manually")
        print("2. Look for any verification emails from Twitter")
        print("3. Consider waiting 24 hours before trying again if Twitter has flagged the IP")
        print("4. Check if the account has any posting restrictions")
        sys.exit(1)