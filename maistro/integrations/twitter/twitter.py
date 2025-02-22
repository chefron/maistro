from datetime import datetime, timezone, date
import os
import logging
from typing import Dict, List, Optional, Tuple
import requests
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv

from maistro.core.memory.types import Memory, SearchResult
from maistro.core.memory.manager import MemoryManager

load_dotenv()
logger = logging.getLogger('maistro.integrations.platforms.twitter')

class TwitterAPI:
    """Handles Twitter API interactions with memory-based caching"""

    def __init__(self, memory_manager):
        self.api_key = os.getenv('TWITTER_API_KEY')
        self.api_secret = os.getenv('TWITTER_API_SECRET')
        self.access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.access_secret = os.getenv('TWITTER_ACCESS_SECRET')

        # Check for missing credentials
        missing_creds = []
        if not self.api_key:
            missing_creds.append("TWITTER_API_KEY")
        if not self.api_secret:
            missing_creds.append("TWITTER_API_SECRET")
        if not self.access_token:
            missing_creds.append("TWITTER_ACCESS_TOKEN")
        if not self.access_secret:
            missing_creds.append("TWITTER_ACCESS_SECRET")

        if missing_creds:
            raise ValueError(f"Missing required Twitter credentials: {', '.join(missing_creds)}")
        
        self.oauth = OAuth1Session(
            client_key=self.api_key,
            client_secret=self.api_secret,
            resource_owner_key=self.access_token,
            resource_owner_secret=self.access_secret
        )

        self.memory = memory_manager

         # Initialize rate limit tracking
        self._update_rate_limits()

    def _update_usage_data(self):
        """Get current rate limits without burning an API read"""
        try:
            response = self.oauth.get("https://api.twitter.com/2/usage/tweets")
            response.raise_for_status()

            usage_data = response.json()['data']

            # Calculate remaining quota
            project_cap = int(usage_data['project_cap'])
            project_usage = int(usage_data['project_usage'])
            remaining_reads = project_cap - project_usage

            # Calculate days until reset
            today = date.today().day
            reset_day = int(usage_data['cap_reset_day'])
            days_until_reset = reset_day - today if reset_day > today else (30 + reset_day - today)

            limits = {
                'reads': {
                    'limit': project_cap,
                    'remaining': remaining_reads,
                    'reset_day': reset_day,
                    'days_until_reset': days_until_reset
                },
                'project_id': usage_data['project_id']
            }

            # Store updated limits
            self.memory.create(
                category="twitter_meta",
                content=str(limits),
                metadata={
                    "type": "usage_limits",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

            return limits
        
        except Exception as e: 
            logger.error(f"Error updating usage data: {e}")
            return None
        
    def _track_api_call(self, response: requests.Response, call_type: str):
        """Update rate limit tracking based on response headers"""
        try:
            limits = {
                'limit': int(response.headers.get('x-rate-limit-limit', 0)),
                'remaining': int(response.headers.get('x-rate-limit-remaining', 0)),
                'reset': int(response.headers.get('x-rate-limit-reset', 0))
            }
            
            current_limits = self.get_rate_limits()
            if current_limits:
                current_limits[call_type] = limits
                
                self.memory.create(
                    category="twitter_meta",
                    content=str(current_limits),
                    metadata={
                        "type": "rate_limits",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
        except Exception as e:
            logger.error(f"Error tracking API call: {e}")

    def get_rate_limits(self) -> Optional[Dict]:
        """Get current rate limits from memory"""
        try:
            results = self.memory.search("twitter_meta", "rate_limits")
            if results:
                return eval(results[0].memory.content)
            return self._update_rate_limits()
        except Exception as e:
            logger.error(f"Error getting rate limits: {e}")
            return None

    def _cache_interaction(self, interaction: Dict, interaction_type: str):
        """Store an interaction in memory"""
        try: 
            self.memory.create(
                category="twitter_interactions",
                content=str(interaction),
                metadata={
                    "tweet_id": interaction["id"],
                    "type": interaction_type,
                    "author": interaction.get("author_id"),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Error caching interaction: {e}")

    def _get_cached_interaction(self, tweet_id: str) -> Optional[Dict]:
        """Retrieve a cached interaction"""



        