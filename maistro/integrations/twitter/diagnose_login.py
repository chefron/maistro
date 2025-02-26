#!/usr/bin/env python3
"""
Diagnostic script for Twitter login issues.
This script attempts to diagnose login problems with the Twitter API.

Usage:
    python diagnose_login.py

The script reads Twitter credentials from the .env file in the project root.
"""

import sys
import os
import time
import random
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from scraper import TwitterScraper

# Load environment variables from .env file in project root
project_root = Path(__file__).resolve().parents[3]  # Go up 3 levels from the script
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

def diagnose_login_issues():
    """Diagnose Twitter login issues with detailed logging"""
    print("=== Twitter Login Diagnostic Tool ===")
    
    # Get credentials from environment variables
    username = os.getenv('TWITTER_USERNAME')
    password = os.getenv('TWITTER_PASSWORD')
    email = os.getenv('TWITTER_EMAIL')
    
    if not username or not password:
        print("Error: TWITTER_USERNAME and TWITTER_PASSWORD must be set in the .env file")
        sys.exit(1)
    
    print(f"Username: {username}")
    print(f"Email provided: {'Yes' if email else 'No'}")
    
    # Create a session with minimal fingerprinting
    session = requests.Session()
    session.verify = False
    
    # Suppress InsecureRequestWarning
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Use a stable, common user agent
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    
    # Basic headers for guest token request
    headers = {
        'authorization': f'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        'User-Agent': user_agent,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/json',
        'Referer': 'https://twitter.com/',
        'Origin': 'https://twitter.com',
    }
    
    # Step 1: Check Twitter API status
    print("\n=== Step 1: Checking Twitter API Status ===")
    try:
        response = session.get('https://api.twitter.com/1.1/help/configuration.json', 
                              headers=headers, timeout=10)
        print(f"API Status Check: {response.status_code}")
        if response.status_code == 200:
            print("✅ Twitter API appears to be operational")
        else:
            print(f"⚠️ Twitter API returned status code {response.status_code}")
    except Exception as e:
        print(f"❌ Error connecting to Twitter API: {e}")
    
    # Step 2: Get guest token
    print("\n=== Step 2: Getting Guest Token ===")
    guest_token = None
    try:
        response = session.post(
            'https://api.twitter.com/1.1/guest/activate.json',
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            guest_token = response.json().get("guest_token", "")
            print(f"✅ Successfully got guest token: {guest_token[:5]}...")
            headers['x-guest-token'] = guest_token
        else:
            print(f"❌ Failed to get guest token: {response.status_code}")
            if response.status_code == 429:
                print("⚠️ Rate limited by Twitter. This could indicate IP-based blocking.")
    except Exception as e:
        print(f"❌ Error getting guest token: {e}")
    
    if not guest_token:
        print("Cannot proceed without guest token. Exiting.")
        return
    
    # Step 3: Check account status
    print("\n=== Step 3: Checking Account Status ===")
    try:
        # Initiate login flow
        flow_data = {
            'flow_name': 'login',
            'input_flow_data': {
                'flow_context': {
                    'debug_overrides': {},
                    'start_location': {'location': 'splash_screen'}
                }
            }
        }
        
        response = session.post(
            'https://api.twitter.com/1.1/onboarding/task.json',
            headers=headers,
            json=flow_data,
            timeout=10
        )
        
        if response.status_code == 200:
            print("✅ Successfully initiated login flow")
            flow_token = response.json().get('flow_token')
            
            # Handle JS instrumentation
            print("\nHandling JS instrumentation...")
            js_response = json.dumps({
                "rf": {
                    "af07339bbc6d24bbe2c262bbd79d59f3a6559c63585c543e5c19a4031df5aba7": 86,
                    "a5a3a5a71b297a0f3c824d4f56f4598f3e7b46d6e883be25e39d38e4a0e8c3d7": 251
                },
                "s": "iAGgWGVXHAXkdQEbRDHjVHcQ9dGE-MTY3NzI2MjI5OTQwNQkxMWUyMGE2MWE4ZWI5OTI5ZmE3YzI4NjQwYmJlNDVlNzMKCTFhNmM5ZGE0YWRlYzk0ZWNmZGIzMDg5YTJiMjkyNGVlCgkwYmNiOTdlZmVlNDQ5YWVjOTZiMjA4YTJiMjkyNGVlCglmYWxzZQF4vGnHIXFKXPtRNpgBT_Xj9Q=="
            })
            
            js_data = {
                'flow_token': flow_token,
                'subtask_inputs': [{
                    'subtask_id': 'LoginJsInstrumentationSubtask', 
                    'js_instrumentation': {
                        'response': js_response, 
                        'link': 'next_link'
                    }
                }]
            }
            
            response = session.post(
                'https://api.twitter.com/1.1/onboarding/task.json',
                headers=headers,
                json=js_data,
                timeout=10
            )
            
            if response.status_code == 200:
                print("✅ Successfully handled JS instrumentation")
                flow_token = response.json().get('flow_token')
                
                # Submit username
                print("\nSubmitting username...")
                username_data = {
                    'flow_token': flow_token,
                    'subtask_inputs': [{
                        'subtask_id': 'LoginEnterUserIdentifierSSO', 
                        'settings_list': {
                            'setting_responses': [{
                                'key': 'user_identifier', 
                                'response_data': {
                                    'text_data': {'result': username}
                                }
                            }], 
                            'link': 'next_link'
                        }
                    }]
                }
                
                response = session.post(
                    'https://api.twitter.com/1.1/onboarding/task.json',
                    headers=headers,
                    json=username_data,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Check for DenyLoginSubtask
                    if 'subtasks' in result:
                        subtask_ids = [subtask.get('subtask_id') for subtask in result.get('subtasks', [])]
                        print(f"Received subtasks: {subtask_ids}")
                        
                        if 'DenyLoginSubtask' in subtask_ids:
                            print("❌ Twitter is actively denying login for this account")
                            
                            # Extract error message if available
                            for subtask in result.get('subtasks', []):
                                if subtask.get('subtask_id') == 'DenyLoginSubtask':
                                    errors = subtask.get('errors', [])
                                    if errors:
                                        error_message = errors[0].get('message', 'Unknown error')
                                        print(f"Error message: {error_message}")
                            
                            print("\n=== Diagnosis ===")
                            print("Twitter is actively blocking login attempts for this account. Possible reasons:")
                            print("1. Account may be temporarily locked due to suspicious activity")
                            print("2. Twitter may have detected automated login attempts")
                            print("3. Account may require additional verification")
                            print("4. IP address may be flagged by Twitter's anti-bot systems")
                            
                            print("\n=== Recommendations ===")
                            print("1. Try logging in manually through the Twitter website to verify account status")
                            print("2. Check email for any messages from Twitter about account security")
                            print("3. If account is locked, follow Twitter's recovery process")
                            print("4. Wait 24 hours before attempting automated login again")
                            print("5. Consider using a different IP address or proxy")
                        else:
                            print("✅ Account appears to be in good standing")
                    else:
                        print("⚠️ Unexpected response format after submitting username")
                else:
                    print(f"❌ Failed to submit username: {response.status_code}")
            else:
                print(f"❌ Failed to handle JS instrumentation: {response.status_code}")
        else:
            print(f"❌ Failed to initiate login flow: {response.status_code}")
    except Exception as e:
        print(f"❌ Error checking account status: {e}")
    
    # Step 4: Check IP reputation
    print("\n=== Step 4: Checking IP Reputation ===")
    try:
        # Make a simple request to check if we're being rate limited
        response = session.get(
            'https://api.twitter.com/1.1/help/settings.json',
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 429:
            print("❌ IP address is being rate limited by Twitter")
            print("This suggests your IP may be flagged for suspicious activity")
            retry_after = response.headers.get('retry-after')
            if retry_after:
                print(f"Twitter suggests waiting {retry_after} seconds before retrying")
        elif response.status_code == 403:
            print("❌ IP address may be blocked or restricted by Twitter")
        else:
            print(f"IP reputation check: Status code {response.status_code}")
            if response.status_code < 400:
                print("✅ IP address does not appear to be blocked")
            else:
                print("⚠️ IP address may have restrictions")
    except Exception as e:
        print(f"❌ Error checking IP reputation: {e}")
    
    print("\n=== Diagnostic Summary ===")
    print("Based on the diagnostic tests, here are the likely issues:")
    
    # Try using the original scraper with a different approach
    print("\n=== Attempting Alternative Login Approach ===")
    print("This will try to login with modified parameters to bypass restrictions...")
    
    # Create a new scraper instance
    scraper = TwitterScraper()
    
    # Modify some parameters to try to bypass restrictions
    scraper.min_delay = 2.0
    scraper.max_delay = 5.0
    
    # Try login with a longer timeout
    success = scraper.login(username, password, email)
    
    if success:
        print("\n✅ Alternative login approach SUCCEEDED!")
        print("The issue appears to be related to timing or request patterns.")
    else:
        print("\n❌ Alternative login approach also failed.")
        print("The issue is likely related to account restrictions or IP blocking.")
        
    print("\n=== Final Recommendations ===")
    print("1. Try logging in manually through the Twitter website")
    print("2. Check email for any account verification requirements")
    print("3. Wait 24 hours before attempting automated login again")
    print("4. Consider using a different IP address or proxy")
    print("5. If using a shared IP (like a VPS), it may be flagged due to other users")

if __name__ == "__main__":
    diagnose_login_issues()
