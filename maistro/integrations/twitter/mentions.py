#!/usr/bin/env python3
"""
This module processes mentions of the Twitter bot and generates responses.

To use it:
1. Initialize MentionsHandler with an authenticated TwitterAuth instance
2. Call check_mentions() to process new mentions and respond
"""

import os
import time
import logging
import random
import threading
import json
import urllib.parse
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime

from auth import TwitterAuth
from post import TwitterPost
from utils import TwitterError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('twitter_mentions')

class MentionsHandler:
    """Handles Twitter mentions and generates responses"""
    # Search endpoint for mentions
    GRAPHQL_SEARCH_URL = "https://x.com/i/api/graphql/U3QTLwGF8sZCHDuWIMSAmg/SearchTimeline"

    def __init__(self, auth: TwitterAuth):
        """Initialize the mentions handler with an authenticated TwitterAuth instance."""
        self.auth = auth
        if not self.auth.csrf_token or not self.auth.username:
            raise TwitterError ("Not authenticated. Please login first.")
        
        self.username = self.auth.username
        self.poster = TwitterPost(auth)

        # Create cache directory if it doesn't exist
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)

        # Load previously processed mentions
        self.last_checked_id = self._load_last_checked_id()

        logger.info(f"Initialized MentionsHandler for user @{self.username}")
        logger.info(f"Last checked mention ID: {self.last_checked_id}")

    def _get_cache_path(self) -> str:
        """Get the path to the cache file for the last checked mention ID."""
        return os.path.join(self.cache_dir, f"{self.username}_last_mention.txt")
    
    def _load_last_checked_id(self) -> Optional[str]:
        """Load the ID of the last checked mention from cache."""
        try:
            cache_path = self._get_cache_path()
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    return f.read().strip()
            return None
        except Exception as e:
            logger.error(f"Error loading last checked mention ID: {e}")
            return None
        
    def _save_last_checked_id(self, mention_id: str) -> None:
        """Save the ID of the last checked mention to cache."""
        try:
            cache_path = self._get_cache_path()
            with open(cache_path, 'w') as f:
                f.write(mention_id)
            logger.info(f"Updated last checked mention ID: {mention_id}")
        except Exception as e:
            logger.error(f"Error saving last checked mention ID: {e}")

    def fetch_mentions(self, count: int = 20) -> List[Dict[str, Any]]:
        """Fetch recent mentions using the GraphQL API"""
        logger.info(f"Fetching up to {count} mentions for @{self.username}")

        # Required GraphQL variables
        variables = {
            "rawQuery": f"@{self.username}",
            "count": count,
            "querySource": "typed_query",
            "product": "Latest"  # Always use Latest for mentions
        }

        # Add cursor if we have one (for pagination)
        if self.last_checked_id:
            variables["cursor"] = self.last_checked_id

        # GraphQL features parameter (required)
        features = {
            "profile_label_improvements_pcf_label_in_post_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "premium_content_api_read_enabled": False,
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
            "responsive_web_grok_analyze_post_followups_enabled": True,
            "responsive_web_jetfuel_frame": False,
            "responsive_web_grok_share_attachment_enabled": True,
            "articles_preview_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "responsive_web_grok_analysis_button_from_backend": True,
            "creator_subscriptions_quote_tweet_preview_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_grok_image_annotation_enabled": False,
            "responsive_web_enhance_cards_enabled": False
        }

        # Field toggles parameter
        field_toggles = {
            "withArticleRichContentState": False
        }

        # Properly URL-encode the JSON parameters
        vars_json = urllib.parse.quote(json.dumps(variables))
        features_json = urllib.parse.quote(json.dumps(features))
        field_toggles_json = urllib.parse.quote(json.dumps(field_toggles))

        # Construct the URL with query parameters
        url = f"{self.GRAPHQL_SEARCH_URL}?variables={vars_json}&features={features_json}&fieldToggles={field_toggles_json}"

        # Set up headers required for GraphQL requests
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': f'Bearer {self.auth.BEARER_TOKEN}',
            'content-type': 'application/json',
            'x-twitter-active-user': 'yes',
            'x-twitter-auth-type': 'OAuth2Session',
            'x-twitter-client-language': 'en',
            'x-csrf-token': self.auth.csrf_token,
            'referer': f'https://x.com/search?q=%40{self.username}&src=typed_query'
        }

        try:
            # Make the request using the auth object's request method
            response = self.auth.make_request('GET', url, headers=headers)
            
            # Check if the response was successful
            if response.status_code != 200:
                logger.error(f"Failed to fetch mentions: {response.status_code} - {response.text}")
                return []
                
            data = response.json()
            
            # Debug the response structure
          #  logger.debug(f"Response structure: {json.dumps(list(data.keys()))}")

            # Log the full API response for debugging
            logger.info(f"Full API response: {json.dumps(data, indent=2)}")
            
            # Process the response to extract mentions
            mentions = []
            
            # Process the response data structure
            if "data" in data and "search_by_raw_query" in data["data"]:
                search_data = data["data"]["search_by_raw_query"]
                
                if "search_timeline" in search_data and "timeline" in search_data["search_timeline"]:
                    timeline = search_data["search_timeline"]["timeline"]
                    
                    if "instructions" in timeline:
                        for instruction in timeline["instructions"]:
                            if instruction.get("type") == "TimelineAddEntries":
                                entries = instruction.get("entries", [])
                                
                                for entry in entries:
                                    # Skip non-tweet entries like "cursor" entries
                                    if not entry.get("entryId", "").startswith("tweet-"):
                                        continue
                                        
                                    # Tweet content is nested deeply in the GraphQL response
                                    content = entry.get("content", {})
                                    item_content = content.get("itemContent", {})
                                    tweet_results = item_content.get("tweet_results", {})
                                    result = tweet_results.get("result", {})
                                    
                                    # Tweets can be in different formats
                                    if "legacy" in result:
                                        tweet = result["legacy"]
                                        tweet_id = tweet.get("id_str")
                                        
                                        # Skip tweets by the bot itself
                                        if tweet.get("user_id_str") == self.auth.user_id:
                                            continue
                                        
                                        # Extract user information
                                        user = None
                                        user_id = None
                                        username = None
                                        name = None
                                        
                                        # User info can be in different places
                                        if "core" in result and "user_results" in result["core"]:
                                            user_results = result["core"]["user_results"]
                                            if "result" in user_results and "legacy" in user_results["result"]:
                                                user = user_results["result"]["legacy"]
                                                user_id = user.get("id_str")
                                                username = user.get("screen_name")
                                                name = user.get("name")
                                                
                                        mention = {
                                            "id": tweet_id,
                                            "text": tweet.get("full_text", ""),
                                            "created_at": tweet.get("created_at"),
                                            "user_id": user_id,
                                            "username": username,
                                            "name": name,
                                            "in_reply_to_status_id": tweet.get("in_reply_to_status_id_str"),
                                            "in_reply_to_user_id": tweet.get("in_reply_to_user_id_str"),
                                        }
                                        mentions.append(mention)
            
            # Sort mentions by ID (chronological order)
            mentions.sort(key=lambda x: x["id"])
            
            logger.info(f"Fetched {len(mentions)} mentions")
            return mentions
            
        except Exception as e:
            logger.error(f"Error fetching mentions: {e}")
            return []

    def generate_reply(self, mention: Dict[str, Any]) -> str:
        """Generate a reply to a mention."""
        # Extract the mention text and remove the bot's username
        text = mention["text"]
        username = mention["username"]

        # Simple response logic
        if "hello" in text.lower() or "hi" in text.lower():
            return f"Hi @{username}! 👋 Thanks for reaching out!"
        
        if "help" in text.lower():
            return f"@{username} I'm a bot that posts content at regular intervals. You can interact with me by mentioning me in a tweet."
        
        if "thanks" in text.lower() or "thank you" in text.lower():
            return f"@{username} You're welcome! Happy to assist."
            
        if "what can you do" in text.lower():
            return f"@{username} I can post tweets on a schedule, respond to mentions, and have simple conversations!"
        
        # Default response for other mentions
        responses = [
            f"@{username} Thanks for the mention! I'm just a simple bot but I appreciate the interaction.",
            f"@{username} Hello there! I noticed your mention. How can I help?",
            f"@{username} I see you mentioned me. I'm still learning, but I'm happy to chat!",
            f"@{username} Thanks for reaching out! I'm a bot in development, but I'll do my best to respond.",
        ]
        
        return random.choice(responses)

    def process_mention(self, mention: Dict[str, Any]) -> bool:
        """
        Process a single mention and generate a reply.
        
        Args:
            mention: The mention to process
            
        Returns:
            True if the mention was successfully processed, False otherwise
        """
        try:
            # Get mention details
            mention_id = mention["id"]
            username = mention["username"]
            
            logger.info(f"Processing mention {mention_id} from @{username}")

            # Generate reply
            reply = self.generate_reply(mention)

            # Post the reply
            logger.info(f"Replying to tweet {mention_id}: {reply}")
            result = self.poster.create_tweet(reply, mention_id)

            # Update last checked ID if this ID is newer
            if not self.last_checked_id or mention_id > self.last_checked_id:
                self._save_last_checked_id(mention_id)
                
            logger.info(f"Successfully replied to mention {mention_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing mention: {e}")
            return False

    def check_mentions(self) -> int:
        """
        Check for new mentions and respond to them.
        
        Returns:
            Number of mentions successfully processed
        """
        try:
            # Fetch recent mentions
            mentions = self.fetch_mentions()
            
            if not mentions:
                logger.info("No new mentions found")
                return 0
                
            # Process each mention
            processed_count = 0
            for mention in mentions:
                success = self.process_mention(mention)
                if success:
                    processed_count += 1
                    
            logger.info(f"Processed {processed_count} out of {len(mentions)} mentions")
            return processed_count
            
        except Exception as e:
            logger.error(f"Error checking mentions: {e}")
            return 0

# Global variables for the mentions checker
_mentions_running = False
_mentions_thread = None

def _mentions_loop(auth: TwitterAuth, interval: int = 120):
    """
    Main loop for checking mentions at regular intervals.
    
    Args:
        auth: Authenticated TwitterAuth instance
        interval: Time between mention checks in seconds
    """
    global _mentions_running
    _mentions_running = True
    
    # Create the mentions handler
    handler = MentionsHandler(auth)
    
    try:
        while _mentions_running:
            # Check for new mentions
            processed = handler.check_mentions()
            
            # Wait for the next interval
            next_check = datetime.now().timestamp() + interval
            readable_time = datetime.fromtimestamp(next_check).strftime('%Y-%m-%d %H:%M:%S')
            
            if processed > 0:
                logger.info(f"Processed {processed} mentions. Next check at {readable_time}")
            else:
                logger.info(f"No new mentions. Next check at {readable_time}")
                
            # Wait for the next interval
            time.sleep(interval)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping mentions checker.")
        _mentions_running = False
        
    logger.info("Mentions checker stopped")

def start_mentions_checker(auth: TwitterAuth, interval: int = 120) -> threading.Thread:
    """
    Start the mentions checker in a background thread.
    
    Args:
        auth: Authenticated TwitterAuth instance
        interval: Time between mention checks in seconds
        
    Returns:
        threading.Thread: The mentions checker thread
    """
    global _mentions_thread, _mentions_running
    
    if _mentions_running:
        logger.warning("Mentions checker is already running")
        return _mentions_thread
    
    logger.info(f"Starting mentions checker in the background (interval: {interval/60:.1f} minutes)")
    
    _mentions_thread = threading.Thread(
        target=_mentions_loop,
        args=(auth, interval),
        daemon=True
    )
    _mentions_thread.start()
    
    return _mentions_thread

def stop_mentions_checker() -> bool:
    """
    Stop the mentions checker if it's running.
    
    Returns:
        True if the mentions checker was running and is now stopping, False otherwise
    """
    global _mentions_running
    
    if _mentions_running:
        logger.info("Stopping mentions checker...")
        _mentions_running = False
        return True
    else:
        logger.warning("Mentions checker is not running")
        return False






















