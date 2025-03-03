import random
import time
import json
import base64
import os
import uuid
from typing import Dict, Callable, List, Optional

from auth import TwitterAuth
from utils import TwitterError

class TwitterPost:
    """Handles posting tweets and other content to Twitter"""
    
    def __init__(self, auth: TwitterAuth):
        """
        Initialize with an authenticated TwitterAuth instance
        
        Args:
            auth: An authenticated TwitterAuth instance
        """
        self.auth = auth
        if not self.auth.csrf_token or not self.auth.username:
            raise TwitterError("Not authenticated. Please login first.")
    
    def create_tweet(self, text: str) -> Dict:
        """
        Create a new tweet using Twitter GraphQL API.
        
        Args:
            text: The text content of the tweet
                
        Returns:
            Dict: Response from Twitter API
        """
        if not self.auth.csrf_token:
            raise TwitterError("Not authenticated. Please login first.")
        
        # Simulate more realistic browsing before tweeting
        try:
            print("Simulating browsing behavior before tweeting...")
            
            # First get the home timeline
            print("Visiting home timeline...")
            self.auth.make_request('GET', "https://twitter.com/home")
            
            # Initial timeline reading pause
            initial_reading = random.uniform(6.0, 13.0)
            print(f"Reading initial tweets for {initial_reading:.2f} seconds...")
            time.sleep(initial_reading)
            
            # Simulate scrolling down by requesting more tweets with a cursor
            # This mimics the "load more" functionality when scrolling
            print("Scrolling down timeline...")
            scroll_requests = random.randint(1, 3)  # Random number of scrolls
            
            for i in range(scroll_requests):
                # In a real scenario, we would use the cursor from previous response
                # Since we're just simulating, we can use a timestamp-based approach
                cursor = str(int(time.time() * 1000))
                timeline_url = f"https://twitter.com/i/api/2/timeline/home.json?count=20&cursor={cursor}"
                self.auth.make_request('GET', timeline_url)
                
                # Pause between scrolls
                scroll_pause = random.uniform(1.5, 4.0)
                print(f"Reading more tweets for {scroll_pause:.2f} seconds...")
                time.sleep(scroll_pause)
            
            # Then visit the compose page
            print("Opening compose tweet page...")
            self.auth.make_request('GET', "https://twitter.com/compose/post")
            
        except Exception as e:
            # Just log and continue if this fails
            print(f"Browsing simulation failed (continuing anyway): {e}")
        
        # Add a small random delay before posting (simulates typing/thinking)
        thinking_time = random.uniform(10.0, 19.0)
        print(f"Composing tweet for {thinking_time:.2f} seconds...")
        time.sleep(thinking_time)
        
        print(f"\nAttempting to create tweet: {text}")
    
        # Use the correct GraphQL endpoint and query ID
        url = "https://twitter.com/i/api/graphql/UYy4T67XpYXgWKOafKXB_A/CreateTweet" 
        
        # Build a tweet request payload for GraphQL API
        variables = {
            "tweet_text": text,
            "dark_request": False,
            "media": {
                "media_entities": [],
                "possibly_sensitive": False,
            },
            "semantic_annotation_ids": [],
            "disallowed_reply_options": None,
        }
        
        # Generate a stable client UUID if we don't have one
        if not hasattr(self, 'client_uuid'):
            import uuid
            self.client_uuid = str(uuid.uuid4())
            print(f"Generated client UUID: {self.client_uuid}")
        
        # Generate a transaction ID similar to the one observed
        import base64
        transaction_id_bytes = os.urandom(48)  # Generate random bytes
        transaction_id = base64.b64encode(transaction_id_bytes).decode('utf-8')
        transaction_id = transaction_id.replace('+', '').replace('/', '')[:72]
        
        # Set up tweet-specific headers based on the real request
        tweet_headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': f'Bearer {self.auth.BEARER_TOKEN}',
            'content-type': 'application/json',
            'priority': 'u=1, i',
            'origin': 'https://twitter.com',
            'referer': 'https://twitter.com/compose/post',  # Specific referer for tweet composition
            'sec-ch-ua': '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36',
            'x-client-transaction-id': transaction_id,
            'x-client-uuid': self.client_uuid,
            'x-csrf-token': self.auth.csrf_token,
            'x-twitter-active-user': 'yes',
            'x-twitter-auth-type': 'OAuth2Session',  # Changed from OAuth2Client to OAuth2Session
            'x-twitter-client-language': 'en',
        }
        
        # Features object required by the GraphQL API - use the EXACT features from the real request
        features = {
            "premium_content_api_read_enabled": False,
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
            "responsive_web_grok_analyze_post_followups_enabled": True,
            "responsive_web_jetfuel_frame": False,
            "responsive_web_grok_share_attachment_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "responsive_web_grok_analysis_button_from_backend": True,
            "creator_subscriptions_quote_tweet_preview_enabled": False,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "profile_label_improvements_pcf_label_in_post_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "articles_preview_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "responsive_web_grok_image_annotation_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_enhance_cards_enabled": False,
        }
        
        # Complete payload - including queryId
        payload = {
            "variables": variables,
            "features": features,
            "queryId": "UYy4T67XpYXgWKOafKXB_A"  # Include the query ID
        }
        
        try:
            print("Sending tweet request to GraphQL API endpoint...")
            response = self.auth.make_request('POST', url, json=payload, headers=tweet_headers)
            result = response.json()
            
            print(f"Tweet creation response: {json.dumps(result, indent=2)}")

            # Add more realistic post-tweet behavior
            post_tweet_delay = random.uniform(2.0, 5.0)
            print(f"Adding post-tweet delay of {post_tweet_delay:.2f} seconds...")
            time.sleep(post_tweet_delay)
            
            return result
        except Exception as e:
            print(f"Failed to create tweet: {e}")
            raise TwitterError(f"Failed to create tweet: {e}")
        
    @staticmethod
    def generate_random_tweet(
        templates: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        hashtags: Optional[List[str]] = None
    ) -> str:
        """
        Generate a random tweet based on templates, topics, and hashtags.
        
        Args:
            templates: List of tweet templates with {topic} and {hashtag} placeholders
            topics: List of topics to randomly choose from
            hashtags: List of hashtags to randomly choose from
            
        Returns:
            str: Randomly generated tweet text
        """
        # Default templates if none provided
        if templates is None:
            templates = [
                "Just thinking about {topic} today. Can't stop. Won't stop.",
                "I wonder if anyone else is interested in {topic}? Probably nothing. #{hashtag}",
                "Been researching {topic} lately. Any recommendations? Hook a brother up!",
                "{topic} is effing fascinating. What do you think, fellow kids?",
                "Looking for resources on {topic}. Gimme your best",
                "What's your take on {topic}? I'm curious to hear opinions. Just kidding, I don't care.",
                "The more I learn about {topic}, the more questions I have...",
                "Anyone working with {topic} these days? Hit me up. #{hashtag}"
            ]
        
        # Default topics if none provided
        if topics is None:
            topics = [
                "artificial intelligence", "machine learning", "data science",
                "natural language processing", "computer vision", "robotics",
                "blockchain", "virtual reality", "augmented reality",
                "cloud computing", "edge computing", "quantum computing",
                "cybersecurity", "the future of work", "sustainable technology"
            ]
        
        # Default hashtags if none provided
        if hashtags is None:
            hashtags = [
                "TechTalk", "Innovation", "FutureTech", "DigitalTransformation",
                "TechTrends", "AI", "ML", "DataScience", "TechnologyNews",
                "FutureThinking", "TechInsights", "DigitalFuture"
            ]
        
        # Choose random elements
        template = random.choice(templates)
        topic = random.choice(topics)
        hashtag = random.choice(hashtags)
        
        # Format and return the tweet
        return template.format(topic=topic, hashtag=hashtag)
