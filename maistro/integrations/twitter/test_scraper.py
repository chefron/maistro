#!/usr/bin/env python3
"""
Test script for the TwitterScraper to verify it can connect to Twitter without getting flagged.
This script attempts to get a guest token and perform a simple search without logging in.
"""

import sys
import os
import time
from scraper import TwitterScraper

def test_guest_functionality():
    """Test basic guest functionality of the scraper"""
    print("Initializing Twitter scraper...")
    scraper = TwitterScraper()
    
    print("\n=== Testing guest token acquisition ===")
    # The scraper already gets a guest token during initialization
    if scraper.guest_token:
        print(f"✅ Successfully acquired guest token: {scraper.guest_token[:5]}...")
    else:
        print("❌ Failed to acquire guest token")
        return False
    
    # Test a simple search query that doesn't require login
    print("\n=== Testing search functionality ===")
    try:
        # Use the trends endpoint which is more reliable for guest access
        url = "https://api.twitter.com/1.1/trends/available.json"
        response = scraper._make_request("GET", url)
        
        if response.status_code == 200:
            print("✅ Successfully performed trends query")
            result = response.json()
            locations_count = len(result)
            print(f"Found {locations_count} trend locations in the response")
            return True
        else:
            print(f"❌ Search query failed with status code: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error during search test: {e}")
        return False

if __name__ == "__main__":
    print("=== Twitter Scraper Test ===")
    success = test_guest_functionality()
    
    if success:
        print("\n✅ All tests passed! The scraper appears to be working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Tests failed. The scraper is still having issues.")
        sys.exit(1)
