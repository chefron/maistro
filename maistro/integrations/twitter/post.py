import random
import time
import json
from typing import Dict

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
        
        # First, simulate browsing behavior by fetching timeline
        try:
            print("Simulating browsing behavior before tweeting...")
            timeline_url = "https://twitter.com/i/api/2/timeline/home.json?count=20"
            self.auth.make_request('GET', timeline_url)
        except Exception as e:
            # Just log and continue if this fails, it's just to mimic natural behavior
            print(f"Timeline fetch failed (continuing anyway): {e}")
        
        # Add a small random delay before posting (simulates typing/thinking)
        thinking_time = random.uniform(5.0, 15.0)
        print(f"Adding pre-tweet delay of {thinking_time:.2f} seconds...")
        time.sleep(thinking_time)
        
        print(f"\nAttempting to create tweet: {text}")
        url = "https://twitter.com/i/api/graphql/a1p9RWpkYKBjWv_I3WzS-A/CreateTweet"
        
        # Build a tweet request payload for GraphQL API
        variables = {
            "tweet_text": text,
            "dark_request": False,
            "media": {
                "media_entities": [],
                "possibly_sensitive": False,
            },
            "semantic_annotation_ids": []
        }
        
        # Set up tweet-specific headers
        tweet_headers = self.auth.headers.copy()
        tweet_headers.update({
            'content-type': 'application/json',
            'x-twitter-auth-type': 'OAuth2Client',
            'x-csrf-token': self.auth.csrf_token,
            'authorization': f'Bearer {self.auth.BEARER_TOKEN}',
            'x-twitter-client-language': 'en',
            'referer': 'https://twitter.com/home',
            'origin': 'https://twitter.com',
            'x-twitter-active-user': 'yes',
            # More realistic transaction ID format
            'x-client-transaction-id': f"01{''.join(random.choices('0123456789abcdef', k=16))}",
            # Add more browser-like headers
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': random.choice(['"Windows"', '"macOS"', '"Linux"']),
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
        })
        
        # Add auth token from cookies if available
        if 'auth_token' in self.auth.cookies:
            auth_token = self.auth.cookies['auth_token']
            tweet_headers['cookie'] = f'auth_token={auth_token}; ct0={self.auth.csrf_token}'
        
        # Features object required by the GraphQL API
        features = {
            "interactive_text_enabled": True,
            "longform_notetweets_inline_media_enabled": False,
            "responsive_web_text_conversations_enabled": False,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
            "vibe_api_enabled": False,
            "rweb_lists_timeline_redesign_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "responsive_web_enhance_cards_enabled": False,
            "subscriptions_verification_info_enabled": True,
            "subscriptions_verification_info_reason_enabled": True,
            "subscriptions_verification_info_verified_since_enabled": True,
            "super_follow_badge_privacy_enabled": False,
            "super_follow_exclusive_tweet_notifications_enabled": False,
            "super_follow_tweet_api_enabled": False,
            "super_follow_user_api_enabled": False,
            "android_graphql_skip_api_media_color_palette": False,
            "creator_subscriptions_subscription_count_enabled": False,
            "blue_business_profile_image_shape_enabled": False,
            "unified_cards_ad_metadata_container_dynamic_card_content_query_enabled": False,
            "rweb_video_timestamps_enabled": False,
            "c9s_tweet_anatomy_moderator_badge_enabled": False,
            "responsive_web_twitter_article_tweet_consumption_enabled": False
        }
        
        # Complete payload
        payload = {
            "variables": variables,
            "features": features,
            "fieldToggles": {}
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