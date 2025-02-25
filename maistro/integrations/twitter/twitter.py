import sqlite3
import json
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import requests
from requests_oauthlib import OAuth1

load_dotenv()

class XMusicAgent:
    def __init__(self, agent_name, refresh_interval_minutes=1440): # Default refresh: 1 day (1440 minutes)
        self.agent_name = agent_name
        self.refresh_interval = refresh_interval_minutes * 60  # Convert minutes to seconds
        self.cache_db = f"{agent_name}_cache.db"
        self.usage_log = f"{agent_name}_usage.json"

        # Load API credentials from .env
        self.api_key = os.getenv("TWITTER_API_KEY")
        self.api_secret = os.getenv("TWITTER_API_SECRET")
        self.access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        self.access_secret = os.getenv("TWITTER_ACCESS_SECRET")

        # OAuth 1.0a setup for X API
        self.auth = OAuth1(
            self.api_key,
            client_secret=self.api_secret,
            resource_owner_key=self.access_token,
            resource_owner_secret=self.access_secret
        )

        # API limits (fetched dynamically)
        self.read_limit = None
        self.post_limit = None
        self.reads_remaining = None
        self.posts_remaining = None
        self.reset_time = None # Unix timestamp for limit reset

        # Initialize cache and usage tracking
        self.setup_cache()
        self.load_or_init_usage()

        # Get users ID for mentions endpoint (one-time setup)
        self.user_id = self.get_user_id()

        # Initial read if cache is empty or stale
        if not self.cache.exists() or self.cache_is_stale():
            self.refresh_cache()

    def setup_cache(self):
        """Set up SQLite cache for tweets and replies"""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                timestamp TEXT
            )
        ''')
        conn.commit()
        conn.close
    
    def load_or_init_usage(self):
        """Load or initiate API usage tracking with reset check"""
        now = datetime.now()
        if not os.path.exists(self.usage_log):
            self.usage = {
                "reads": 0,
                "posts": 0,
                "last_reset": now.isoformat(),
                "history": []
            }
            self.save_usage()
        else:
            with open(self.usage_log, 'r') as f:
                self.usage = json.load(f)
            # Check if limits should reset (baesd on last API reset time)
            if self.reset_time and datetime.fromtimestamp(self.reset_time) < now:
                self.usage["reads"] = 0
                self.usage["posts"] = 0
                self.usage["last_reset"] = now.isoformat()
                self.save_usage()
        
    def save_usage(self):
        """Save usage stats to file"""
        with open(self.usage_log, 'w') as f:
            json.dump(self.usage, f, indent=4)

    def cache_exists(self):
        """Check if cache has data"""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cache WHERE key='last_refresh'")
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    
    def cache_is_stale(self):
        """Check if cache is outdated based on refresh interval"""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cache WHERE key='last_refresh'")
        result = cursor.fetchone()
        conn.close()

        if not result:
            return True
        
        last_refresh = datetime.fromisoformat(result[0])
        now = datetime.now()
        time_since_refresh = (now - last_refresh).total_seconds()

        return time_since_refresh > self.refresh_interval
    
    def refresh_cache(self):
        """Fetch fresh data from X and update cache"""
        if self.reads_remaining is not None and self.reads_remaining <= 0:
            print(f"{self.agent_name}: Read limit reached until {datetime.fromtimestamp(self.reset_time)}.")
            return

        url = f"https://api.twitter.com/2/users/{self.user_id}/mentions?max_results=100"
        response = requests.get(url, auth=self.auth)

        if response.status_code == 200:
            self.update_limits_from_headers(response)
            conn = sqlite3.connect(self.cache_db)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
                          ("mentions", response.text, datetime.now().isoformat()))
            cursor.execute("INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
                          ("last_refresh", datetime.now().isoformat(), datetime.now().isoformat()))
            conn.commit()
            conn.close()

            self.usage["reads"] += 1
            self.usage["history"].append({"type": "read", "timestamp": datetime.now().isoformat()})
            self.save_usage()
            print(f"{self.agent_name}: Cache refreshed. Reads remaining: {self.reads_remaining}/{self.read_limit}")
        else:
            print(f"{self.agent_name}: Error refreshing cache - {response.status_code}: {response.text}")
        
