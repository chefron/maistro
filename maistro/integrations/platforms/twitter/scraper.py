from typing import Dict, List, Optional, Any
import aiohttp
import asyncio
import logging
import json
import time
from datetime import datetime, timezone
from urllib.parse import quote
from dataclasses import dataclass
from http.cookies import SimpleCookie

logger = logging.getLogger('maistro.integrations.platforms.twitter')

@dataclass
class Tweet:
    """Represents a Tweet"""
    id: str
    text: str
    user_id: str
    username: str
    name: str
    created_at: datetime
    conversation_id: str
    in_reply_to_status_id: Optional[str] = None
    quoted_status_id: Optional[str] = None
    retweet_count: int = 0
    like_count: int = 0
    reply_count: int = 0
    quote_count: int = 0

class RateLimiter:
    """Rate limiter with exponential backoff"""
    def __init__(self, requests_per_window: int = 50, window_seconds: int = 900):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.requests = []
        self.backoff_until = 0
        self.consecutive_failures = 0

    async def acquire(self):
        """Wait until a request can be made"""
        now = time.time()

        # Clear old requests
        self.requests = [t for t in self.requests if t > now - self.window_seconds]

        # Handle backoff
        if now < self.backoff_until:
            wait_time = self.backoff_until - now
            logger.debug(f"Rate limit backoff: waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            self.backoff_until = 0

        # Wait if we're at the limit
        if len(self.requests) >= self.requests_per_window:
            wait_time = self.requests[0] - (now - self.window_seconds)
            logger.debug(f"Rate limit window full: waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
            self.requests.pop(0)

        self.requests.append(now)

    def backoff(self):
        """Implement exponential backoff after failures"""
        self.consecutive_failures += 1
        backoff_time = min(60 * 2 ** self.consecutive_failures, 3600) # Max 1 hour
        self.backoff_until = time.time() + backoff_time
        logger.warning(f"Implementing backoff for {backoff_time}s after self.consecutive_failures")

    def success(self):
        """Reset failure count after success"""
        self.consecutive_failures = 0
        self.backoff_until = 0
        logger.info("Request succeeded. Failure count reset.")

class TwitterScraper:
    """Base Twitter scraping functionality"""

