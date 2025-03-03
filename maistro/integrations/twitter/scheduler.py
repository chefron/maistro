#!/usr/bin/env python3
"""
Tweet scheduler for Twitter automation.
This module schedules tweets at randomized intervals using an authenticated TwitterAuth instance.

To use this scheduler:
1. Set up the following environment variables:
   - TWEET_MIN_INTERVAL: Minimum time between tweets (in minutes)
   - TWEET_MAX_INTERVAL: Maximum time between tweets (in minutes)

2. Create a content generator function that returns tweet text.

3. Call either:
   - start_scheduler() to begin continuous tweeting in the background
   - schedule_tweets() to run the scheduler in the foreground
"""

import os
import time
import random
import threading
import signal
import sys
from datetime import datetime
from typing import Callable, Dict
import logging

from dotenv import load_dotenv
from auth import TwitterAuth
from post import TwitterPost

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('twitter_scheduler')

load_dotenv()

# Global flag for controlling scheduler loop
_scheduler_running = False
_scheduler_thread = None

def _get_interval_settings() -> Dict[str, int]:
    """Get scheduler interval settings from environment variables with defaults"""
    return {
        'min_interval': int(os.getenv('TWEET_MIN_INTERVAL', '120')),  # minutes
        'max_interval': int(os.getenv('TWEET_MAX_INTERVAL', '300')),  # minutes
    }

def _calculate_next_interval() -> float:
    """Calculate the next randomized interval in seconds"""
    settings = _get_interval_settings()
    min_minutes = settings['min_interval']
    max_minutes = settings['max_interval']
    
    # Ensure max is greater than min
    if max_minutes <= min_minutes:
        max_minutes = min_minutes + 120
    
    # Calculate a random interval in minutes, then convert to seconds
    minutes = random.uniform(min_minutes, max_minutes)
    seconds = minutes * 60
    
    return seconds

def _format_time_until(seconds: float) -> str:
    """Format seconds into a human-readable time string"""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def _scheduler_loop(auth: TwitterAuth, content_generator: Callable[[], str]):
    """
    Main scheduler loop that posts tweets at intervals.
    
    Args:
        auth: Authenticated TwitterAuth instance
        content_generator: Function that returns tweet content
    """
    global _scheduler_running
    _scheduler_running = True
    
    # Create a single TwitterPost instance to use throughout the scheduler
    poster = TwitterPost(auth)
    
    try:
        # Immediately post the first tweet
        try:
            logger.info("Posting initial tweet...")
            tweet_text = content_generator()
            logger.info(f"Posting tweet: {tweet_text}")
            result = poster.create_tweet(tweet_text)
            logger.info(f"Successfully posted tweet")
        except Exception as e:
            logger.error(f"Error posting initial tweet: {e}")
        
        # Then continue with the regular schedule
        while _scheduler_running:
            # Calculate the next interval
            next_interval = _calculate_next_interval()
            next_time = datetime.now().timestamp() + next_interval
            readable_time = datetime.fromtimestamp(next_time).strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"Next tweet in {_format_time_until(next_interval)} at {readable_time}")
            
            # Wait for the next interval
            time.sleep(next_interval)
            
            # Post a tweet
            try:
                tweet_text = content_generator()
                logger.info(f"Posting tweet: {tweet_text}")
                poster.create_tweet(tweet_text)
                logger.info(f"Successfully posted tweet")
            except Exception as e:
                logger.error(f"Error posting tweet: {e}")
                # Wait 5 minutes before trying again after an error
                logger.info("Waiting 5 minutes before retrying...")
                time.sleep(300)
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping scheduler.")
        _scheduler_running = False
        
    logger.info("Tweet scheduler stopped")

def start_scheduler(auth: TwitterAuth, content_generator: Callable[[], str]) -> threading.Thread:
    """
    Start the tweet scheduler in a background thread.
    
    Args:
        auth: Authenticated TwitterAuth instance
        content_generator: Function that returns tweet content
        
    Returns:
        threading.Thread: The scheduler thread
    """
    global _scheduler_thread, _scheduler_running
    
    if _scheduler_running:
        logger.warning("Scheduler is already running")
        return _scheduler_thread
    
    logger.info("Starting tweet scheduler in the background")
    
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        args=(auth, content_generator),
        daemon=True
    )
    _scheduler_thread.start()
    
    return _scheduler_thread

def stop_scheduler():
    """Stop the tweet scheduler if it's running"""
    global _scheduler_running
    
    if _scheduler_running:
        logger.info("Stopping tweet scheduler...")
        _scheduler_running = False
        return True
    else:
        logger.warning("Scheduler is not running")
        return False

def schedule_tweets(
    auth: TwitterAuth, 
    content_generator: Callable[[], str]
):
    """
    Run the tweet scheduler in the foreground.
    
    Args:
        auth: Authenticated TwitterAuth instance
        content_generator: Function that returns tweet content
    """
    # Register signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}. Shutting down...")
        global _scheduler_running
        _scheduler_running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Starting tweet scheduler in the foreground")
    settings = _get_interval_settings()
    logger.info(f"Tweet interval: {settings['min_interval']} to {settings['max_interval']} minutes")
    
    _scheduler_loop(auth, content_generator)