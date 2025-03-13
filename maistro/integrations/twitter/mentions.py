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
from datetime import datetime, timedelta

from auth import TwitterAuth
from utils import TwitterError
from api_post import APITwitterPost
from maistro.core.persona.generator import generate_character_prompt
from conversation_tracker import ConversationTracker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('twitter_mentions')

class MentionsHandler:
    """Handles Twitter mentions and generates responses"""
    # Search endpoint for mentions
    GRAPHQL_SEARCH_URL = "https://x.com/i/api/graphql/U3QTLwGF8sZCHDuWIMSAmg/SearchTimeline"

    def __init__(self, auth: TwitterAuth, conversation_tracker=None):
        """Initialize the mentions handler with an authenticated TwitterAuth instance."""
        self.auth = auth
        if not self.auth.csrf_token or not self.auth.username:
            raise TwitterError("Not authenticated. Please login first.")
        
        self.username = self.auth.username
        
        # First, create cache directory
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)

        # Load cache data after setting up cache_dir
        cache_data = self._load_cache_data()
        self.last_checked_id = cache_data.get('last_checked_id')
        self.processed_tweet_ids = set(cache_data.get('processed_ids', []))
        
        # Initialize conversation tracker after setting up cache_dir
        self.conversation_tracker = ConversationTracker(self.cache_dir, self.username)
        
        # Create poster after initializing conversation_tracker
        self.poster = APITwitterPost(auth, self.conversation_tracker)

        logger.info(f"Initialized MentionsHandler for user @{self.username}")
        logger.info(f"Last checked mention ID: {self.last_checked_id}")
        logger.info(f"Loaded {len(self.processed_tweet_ids)} previously processed tweets")

    def _get_cache_path(self) -> str:
        """Get the path to the cache file for mention tracking data."""
        return os.path.join(self.cache_dir, f"{self.username}_mentions_cache.json")

    def _load_cache_data(self) -> Dict:
        """Load all cache data from a single file."""
        try:
            cache_path = self._get_cache_path()
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)
                    logger.info(f"Loaded cache data with {len(cache_data.get('processed_ids', []))} processed tweets")
                    return cache_data
            return {
                'last_checked_id': None,
                'processed_ids': []
            }
        except Exception as e:
            logger.error(f"Error loading cache data: {e}")
            return {
                'last_checked_id': None,
                'processed_ids': []
            }
            
    def _save_cache_data(self) -> None:
        """Save all cache data to a single file."""
        try:
            cache_path = self._get_cache_path()
            cache_data = {
                'last_checked_id': self.last_checked_id,
                'processed_ids': list(self.processed_tweet_ids)
            }
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f)
            logger.info(f"Saved cache data with {len(self.processed_tweet_ids)} processed tweet IDs")
        except Exception as e:
            logger.error(f"Error saving cache data: {e}")

    def check_mentions(self, agent=None) -> int:
        """
        Check for new mentions and respond to them.
        
        Args:
            agent: Optional MusicAgent instance for AI-generated replies
            
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
                # Skip mentions we've already processed
                if mention["id"] in self.processed_tweet_ids:
                    logger.info(f"Skipping already processed mention {mention['id']} from @{mention['username']}")
                    continue
                    
                success = self.process_mention(mention, agent)
                if success:
                    processed_count += 1
                    
            logger.info(f"Processed {processed_count} out of {len(mentions)} mentions")
            return processed_count
            
        except Exception as e:
            logger.error(f"Error checking mentions: {e}")
            return 0

    def process_mention(self, mention: Dict[str, Any], agent=None) -> bool:
        """
        Process a single mention and generate a reply with conversation context.
        
        Args:
            mention: The mention to process
            agent: Optional MusicAgent instance for AI-generated replies
            
        Returns:
            True if the mention was successfully processed, False otherwise
        """
        try:
            # Get mention details
            mention_id = mention["id"]
            username = mention["username"]
            
            # Skip if we've already processed this mention
            if mention_id in self.processed_tweet_ids:
                logger.info(f"Skipping already processed mention {mention_id} from @{username}")
                return False
            
            logger.info(f"Processing mention {mention_id} from @{username}")
            
            # Add to conversation tracker and get thread ID
            thread_id = self.conversation_tracker.add_mention(mention)
            
            # Get conversation context
            thread_context = self.conversation_tracker.get_thread_context(thread_id)
            
            # Generate reply using the agent and conversation context
            reply = self.generate_reply(mention, agent, thread_context)

            # Post the reply
            logger.info(f"Replying to tweet {mention_id}: {reply}")
            result = self.poster.create_tweet(reply, mention_id)
            
            # Extract tweet ID from API response
            reply_tweet_id = None
            
            if isinstance(result, dict):
                # Official Twitter API v2 response structure
                if "data" in result and "id" in result["data"]:
                    reply_tweet_id = result["data"]["id"]
                else:
                    logger.warning(f"Could not find tweet ID in response structure: {result}")
            
            # If we couldn't get the tweet ID, use a placeholder
            if not reply_tweet_id:
                import time
                reply_tweet_id = f"unknown_{int(time.time())}"
                logger.warning(f"Could not extract tweet ID from response, using placeholder: {reply_tweet_id}")
            else:
                logger.info(f"Successfully extracted reply tweet ID: {reply_tweet_id}")
            
            # Add bot's reply to the conversation thread
            self.conversation_tracker.add_bot_reply(thread_id, reply_tweet_id, reply)

            # Add the tweet ID to the processed set and save
            self.processed_tweet_ids.add(mention_id)
            self._save_cache_data()
            
            # Update last checked ID if this ID is newer
            if not self.last_checked_id or mention_id > self.last_checked_id:
                self.last_checked_id = mention_id
                
            logger.info(f"Successfully replied to mention {mention_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing mention: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def fetch_mentions(self, count: int = 20) -> List[Dict]:
        """Fetch recent mentions using the GraphQL API"""
        logger.info(f"Fetching up to {count} mentions for @{self.username}")

        # Required GraphQL variables
        variables = {
            "rawQuery": f"@{self.username}",
            "count": count,
            "querySource": "typed_query",
            "product": "Latest"  # Always use Latest for mentions
        }

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
                                            "in_reply_to_status_id_str": tweet.get("in_reply_to_status_id_str"),
                                            "in_reply_to_user_id_str": tweet.get("in_reply_to_user_id_str"),
                                            "conversation_id_str": tweet.get("conversation_id_str")
                                        }
                                        mentions.append(mention)
            
            # Sort mentions by ID (chronological order)
            mentions.sort(key=lambda x: x["id"])
            
            logger.info(f"Fetched {len(mentions)} mentions")
            return mentions
            
        except Exception as e:
            logger.error(f"Error fetching mentions: {e}")
            return []

    def generate_reply(self, mention: Dict[str, Any], agent=None, thread_context: str = None) -> str:
        """
        Generate a reply to a mention, using an agent, with conversation context.
        
        Args:
            mention: The mention to generate a reply for
            agent: MusicAgent instance for AI-generated replies
            thread_context: Optional conversation history
            
        Returns:
            The generated reply text
        """
        # Require an agent for generating replies
        if not agent:
            raise ValueError("Agent is required for generating replies")
        
        # Extract the mention text and username
        text = mention["text"]
        username = mention["username"]
        
        # Get current date and time for context
        current_datetime = datetime.now().strftime("%B %d, %Y, %I:%M %p")
        
        # Create a mention-specific prompt using the character generator
        character_prompt, _ = generate_character_prompt(
            config=agent.config,
            artist_name=agent.artist_name,
            client=agent.client
        )
        
        # Add mention-specific instructions with current date/time context
        mention_instructions = f"""

    CURRENT TASK: You're responding to a tweet that mentioned you. Please write a brief and authentic reply.

    The tweet is from: @{username}
    The tweet says: {text}
    Current date and time: {current_datetime}
    """

        # Add current thread context if available
        if thread_context:
            mention_instructions += f"\n\nCURRENT THREAD:\n{thread_context}\n"
        else:
            mention_instructions += "\n\nThis is the start of a new conversation thread.\n"
        
        # Get user history from previous conversations
        user_history = self.conversation_tracker.get_user_history_summary(username)
        if user_history and "No previous conversations" not in user_history:
            mention_instructions += f"\n\n{user_history}\n"

        mention_instructions += """
    - Keep your response casual and conversational.
    - Maintain your unique voice and personality.
    - Respond directly to what they're saying or asking in the current thread.
    - Keep it brief (maximum 250 characters).
    - Be authentic to your character.
    - Don't add commentary or acknowledge this as a request.
    - If relevant, you may subtly reference previous conversations from the history provided.

    Just write the reply text itself with no additional explanation."""
        
        # Rest of the method remains the same...
        
        complete_prompt = character_prompt + mention_instructions
        
        # Debug output - print the entire prompt being sent to the LLM
        print("\n========== MENTION RESPONSE PROMPT SENT TO LLM ==========")
        print(complete_prompt)
        print("=========================================================\n")
        
        # Use the combined prompt instead of system+user separation
        response = agent.client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=150,  # Limit to a short response
            messages=[{"role": "user", "content": complete_prompt}]
        )
        
        response_text = response.content[0].text.strip()
        
        # Ensure response is within character limit
        if len(response_text) > 250:
            response_text = response_text[:247] + "..."
            
        print(f"Generated mention response: {response_text}")
        return response_text

# Global variables for the mentions checker
_mentions_running = False
_mentions_thread = None

def _mentions_loop(auth: TwitterAuth, agent=None, conversation_tracker=None, interval: int = 120):
    """
    Main loop for checking mentions at regular intervals.
    
    Args:
        auth: Authenticated TwitterAuth instance
        agent: Optional MusicAgent instance for AI-generated replies
        interval: Time between mention checks in seconds
    """
    global _mentions_running
    _mentions_running = True
    
    # Create the mentions handler
    handler = MentionsHandler(auth, conversation_tracker)
    
    try:
        while _mentions_running:
            # Check for new mentions
            processed = handler.check_mentions(agent)
            
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

def start_mentions_checker(auth: TwitterAuth, agent=None, conversation_tracker=None, interval: int = 120) -> threading.Thread:
    """
    Start the mentions checker in a background thread.
    
    Args:
        auth: Authenticated TwitterAuth instance
        agent: Optional MusicAgent instance for AI-generated replies
        conversation_tracker: Optional ConversationTracker to share with tweet scheduler
        interval: Time between mention checks in seconds
        
    Returns:
        threading.Thread: The mentions checker thread
    """
    # Pass along to the mentions loop
    _mentions_thread = threading.Thread(
        target=_mentions_loop,
        args=(auth, agent, conversation_tracker, interval),
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



















