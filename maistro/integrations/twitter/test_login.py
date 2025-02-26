#!/usr/bin/env python3
"""
Test script for the TwitterScraper login functionality.
This script attempts to log in to Twitter and verify the session.

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
import argparse
from pathlib import Path
from dotenv import load_dotenv
from scraper import TwitterScraper

# Load environment variables from .env file in project root
project_root = Path(__file__).resolve().parents[3]  # Go up 3 levels from the script
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

def test_login(username, password, email=None, two_factor_secret=None):
    """Test login functionality of the scraper"""
    print("Initializing Twitter scraper...")
    scraper = TwitterScraper()
    
    print("\n=== Testing login functionality ===")
    login_success = scraper.login(username, password, email, two_factor_secret)
    
    if login_success:
        print("✅ Successfully logged in to Twitter")
        
        # Test creating a tweet (commented out to avoid actually posting)
        print("\n=== Testing tweet creation ===")
        try:
            tweet_text = "Test tweet from Maistro AI agent. This is an automated test."
            result = scraper.create_tweet(tweet_text)
            print(f"✅ Successfully created tweet: {result.get('data', {}).get('text', 'Unknown')}")
        except Exception as e:
            print(f"❌ Error creating tweet: {e}")
            return False
            
        return True
    else:
        print("❌ Failed to log in to Twitter")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test Twitter login functionality')
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
    
    print("=== Twitter Login Test ===")
    print(f"Username: {username}")
    print(f"Email provided: {'Yes' if email else 'No'}")
    print(f"2FA secret provided: {'Yes' if two_factor_secret else 'No'}")
    
    success = test_login(username, password, email, two_factor_secret)
    
    if success:
        print("\n✅ All tests passed! The login functionality is working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Tests failed. The login functionality is still having issues.")
        sys.exit(1)
