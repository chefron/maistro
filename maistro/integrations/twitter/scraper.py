from typing import Dict, Optional, Any, List, Tuple
import requests
import json
import time
import random
import ssl
import socket
from http.cookies import SimpleCookie
import pyotp
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

class TLSCipherRandomizingAdapter(HTTPAdapter):
    """Custom HTTP adapter that randomizes TLS ciphers to avoid fingerprinting"""
    
    def __init__(self, *args, **kwargs):
        self.original_ciphers = ':'.join(sorted(ssl._DEFAULT_CIPHERS.split(':')))
        super().__init__(*args, **kwargs)
    
    def init_poolmanager(self, *args, **kwargs):
        # Randomize the cipher order before initializing the connection pool
        self._randomize_ciphers()
        # Create a context with SSL verification disabled
        context = create_urllib3_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)
    
    def _randomize_ciphers(self):
        """Randomize the order of TLS ciphers to avoid fingerprinting"""
        # How many ciphers from the top of the list to shuffle
        top_n_shuffle = 8
        
        cipher_list = self.original_ciphers.split(':')
        # Shuffle the first N ciphers
        top_ciphers = cipher_list[:top_n_shuffle]
        random.shuffle(top_ciphers)
        # Keep the rest in the original order
        remaining_ciphers = cipher_list[top_n_shuffle:]
        
        # Set the new cipher order
        new_ciphers = ':'.join(top_ciphers + remaining_ciphers)
        ssl._DEFAULT_CIPHERS = new_ciphers

class TwitterScraper:
    """Enhanced Twitter scraper with improved session handling and login flow"""

    BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    LOGIN_URL = "https://api.twitter.com/1.1/onboarding/task.json"
    GUEST_TOKEN_URL = "https://api.twitter.com/1.1/guest/activate.json"
    
    # List of realistic user agents to rotate through
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    ]

    def __init__(self):
        print("\nInitializing TwitterScraper...")
        self.session = requests.Session()
        
        # Install the TLS cipher randomizing adapter and disable SSL verification for testing
        self.session.mount('https://', TLSCipherRandomizingAdapter())
        self.session.verify = False
        # Suppress InsecureRequestWarning
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.cookies = {}
        self.user_agent = random.choice(self.USER_AGENTS)
        print(f"Using User-Agent: {self.user_agent}")
        
        self.headers = {
            'authorization': f'Bearer {self.BEARER_TOKEN}',
            'User-Agent': self.user_agent,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'x-twitter-auth-type': 'OAuth2Client',
            'x-twitter-active-user': 'yes',
            'x-twitter-client-language': 'en',
            'Referer': 'https://twitter.com/',
            'Origin': 'https://twitter.com',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
        }
        self.csrf_token = None
        print("Getting guest token...")
        self.guest_token = self._get_guest_token()
        self.headers['x-guest-token'] = self.guest_token
        self.user_id = None
        self.username = None
        
        # Add some randomized delays between requests
        self.min_delay = 1.0
        self.max_delay = 3.0

    def _get_guest_token(self, retries=5) -> str:
        """Retrieve a guest token, retrying if necessary."""
        for attempt in range(retries):
            print(f"Attempt {attempt + 1} to get guest token...")
            
            # Add jitter to avoid detection patterns
            jitter = random.uniform(0.5, 1.5)
            if attempt > 0:
                backoff_time = (2 ** attempt) * jitter
                print(f"Backing off for {backoff_time:.2f} seconds...")
                time.sleep(backoff_time)
            
            try:
                response = self.session.post(
                    self.GUEST_TOKEN_URL, 
                    headers=self.headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    token = response.json().get("guest_token", "")
                    print(f"Successfully got guest token: {token[:5]}...")
                    self._update_cookies(response)
                    return token
                
                print(f"Failed to fetch guest token (attempt {attempt+1}): {response.status_code}")
                
                # If we get a 429 (rate limit), wait longer
                if response.status_code == 429:
                    retry_after = int(response.headers.get('retry-after', 60))
                    print(f"Rate limited. Waiting for {retry_after} seconds...")
                    time.sleep(retry_after)
                    
            except (requests.RequestException, socket.error) as e:
                print(f"Network error during guest token request: {e}")
                
        raise TwitterError("Could not retrieve guest token after retries.")

    def _update_cookies(self, response: requests.Response) -> None:
        """Extract and store session cookies."""
        cookies = SimpleCookie()
        cookie_header = response.headers.get('Set-Cookie', '')
        print(f"\nProcessing cookies from response...")
        
        # First update from the session cookies
        for cookie in self.session.cookies:
            self.cookies[cookie.name] = cookie.value
            if cookie.name == 'ct0':  # CSRF token
                self.csrf_token = cookie.value
                print(f"Found CSRF token from session: {cookie.value[:5]}...")
        
        # Then process any Set-Cookie headers
        if cookie_header:
            for cookie in cookie_header.split(','):
                try:
                    cookies.load(cookie)
                    for key, morsel in cookies.items():
                        self.cookies[key] = morsel.value
                        self.session.cookies.set(key, morsel.value, domain='.twitter.com', path='/')
                        if key == 'ct0':  # CSRF token
                            self.csrf_token = morsel.value
                            print(f"Found CSRF token from header: {morsel.value[:5]}...")
                except Exception as e:
                    print(f"Error processing cookie: {e}")
                    continue
                    
        print(f"Current cookie count: {len(self.cookies)}")

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Handle request execution with error handling."""
        print(f"\nMaking {method} request to {url}")
        
        # Add random delay to mimic human behavior
        delay = random.uniform(self.min_delay, self.max_delay)
        print(f"Adding delay of {delay:.2f} seconds...")
        time.sleep(delay)
        
        # Prepare request headers
        request_headers = self.headers.copy()
        if self.csrf_token:
            request_headers['x-csrf-token'] = self.csrf_token
        
        # Occasionally rotate user agent
        if random.random() < 0.2:  # 20% chance to change user agent
            new_user_agent = random.choice(self.USER_AGENTS)
            if new_user_agent != request_headers['User-Agent']:
                print(f"Rotating User-Agent to: {new_user_agent}")
                request_headers['User-Agent'] = new_user_agent
                self.user_agent = new_user_agent
        
        kwargs.setdefault('headers', request_headers)
        kwargs.setdefault('cookies', self.cookies)
        kwargs.setdefault('timeout', 15)  # Set a reasonable timeout
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                print(f"Response status code: {response.status_code}")
                self._update_cookies(response)

                # Handle different status codes
                if response.status_code == 403:  # Forbidden, likely means guest token expired
                    print("403 Forbidden - Refreshing guest token...")
                    self.guest_token = self._get_guest_token()
                    self.headers['x-guest-token'] = self.guest_token
                    request_headers['x-guest-token'] = self.guest_token
                    kwargs['headers'] = request_headers
                    continue
                    
                elif response.status_code == 429:  # Rate limited
                    retry_after = int(response.headers.get('retry-after', 60))
                    print(f"Rate limited. Waiting for {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                    
                response.raise_for_status()
                return response
                
            except requests.RequestException as e:
                print(f"Request error (attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise TwitterError(f"Request failed after {max_retries} attempts: {e}")
                
                # Add exponential backoff with jitter
                backoff_time = (2 ** attempt) * random.uniform(1.0, 2.0)
                print(f"Backing off for {backoff_time:.2f} seconds...")
                time.sleep(backoff_time)
        
        # This should never be reached due to the exception handling above,
        # but adding as a fallback to satisfy the linter
        raise TwitterError("Request failed with an unknown error")

    def _execute_flow_task(self, data: Dict) -> Dict:
        """Executes login flow steps."""
        print(f"\nExecuting flow task with data type: {type(data).__name__}")
        
        # Don't log sensitive data like passwords
        if isinstance(data, dict) and 'subtask_inputs' in data:
            for subtask in data.get('subtask_inputs', []):
                if 'enter_password' in subtask:
                    print("Flow contains password data (not logging)")
                    break
            else:
                # Only log if no password data
                print(f"Flow task data: {json.dumps(data, indent=2)}")
        else:
            print(f"Flow task data: {json.dumps(data, indent=2)}")
            
        response = self._make_request('POST', self.LOGIN_URL, json=data)
        result = response.json()
        
        # Log the response but redact sensitive information
        if 'subtasks' in result:
            print(f"Flow task response contains {len(result['subtasks'])} subtasks")
            for i, subtask in enumerate(result['subtasks']):
                print(f"  Subtask {i+1}: {subtask.get('subtask_id')}")
        else:
            print(f"Flow task response: {json.dumps(result, indent=2)}")
            
        return result

    def _handle_two_factor_auth(self, flow_token: str, two_factor_secret: str) -> Dict:
        """Handle two-factor authentication challenge."""
        print("Generating 2FA code...")
        totp = pyotp.TOTP(two_factor_secret)
        code = totp.now()
        print(f"Generated 2FA code: {code}")
        
        # Try multiple times with exponential backoff
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                return self._execute_flow_task({
                    'flow_token': flow_token,
                    'subtask_inputs': [{
                        'subtask_id': 'LoginTwoFactorAuthChallenge',
                        'enter_text': {
                            'text': code,
                            'link': 'next_link'
                        }
                    }]
                })
            except Exception as e:
                if attempt < max_attempts - 1:
                    backoff_time = (2 ** attempt) * random.uniform(1.0, 2.0)
                    print(f"2FA attempt {attempt+1} failed: {e}. Retrying in {backoff_time:.2f} seconds...")
                    time.sleep(backoff_time)
                    # Generate a new code if needed
                    code = totp.now()
                    print(f"Generated new 2FA code: {code}")
                else:
                    raise

    def login(self, username: str, password: str, email: Optional[str] = None, two_factor_secret: Optional[str] = None) -> bool:
        """Log in to Twitter and handle the flow."""
        print(f"\nStarting login process for user: {username}")
        print(f"Email provided: {'Yes' if email else 'No'}")
        print(f"2FA secret provided: {'Yes' if two_factor_secret else 'No'}")
        
        # Clear cookies before login to avoid conflicts
        self.session.cookies.clear()
        self.cookies = {}
        
        try:
            # Get a fresh guest token before login
            print("\nRefreshing guest token before login...")
            self.guest_token = self._get_guest_token()
            self.headers['x-guest-token'] = self.guest_token
            
            print("\nInitiating login flow...")
            flow_data = self._execute_flow_task({
                'flow_name': 'login',
                'input_flow_data': {
                    'flow_context': {
                        'debug_overrides': {},
                        'start_location': {'location': 'splash_screen'}
                    }
                }
            })

            print("\nHandling JS instrumentation...")
            # Provide a more realistic JS instrumentation response
            js_response = json.dumps({
                "rf": {
                    "af07339bbc6d24bbe2c262bbd79d59f3a6559c63585c543e5c19a4031df5aba7": 86,
                    "a5a3a5a71b297a0f3c824d4f56f4598f3e7b46d6e883be25e39d38e4a0e8c3d7": 251
                },
                "s": "iAGgWGVXHAXkdQEbRDHjVHcQ9dGE-MTY3NzI2MjI5OTQwNQkxMWUyMGE2MWE4ZWI5OTI5ZmE3YzI4NjQwYmJlNDVlNzMKCTFhNmM5ZGE0YWRlYzk0ZWNmZGIzMDg5YTJiMjkyNGVlCgkwYmNiOTdlZmVlNDQ5YWVjOTZiMjA4YTJiMjkyNGVlCglmYWxzZQF4vGnHIXFKXPtRNpgBT_Xj9Q=="
            })
            
            flow_data = self._execute_flow_task({
                'flow_token': flow_data['flow_token'],
                'subtask_inputs': [{
                    'subtask_id': 'LoginJsInstrumentationSubtask', 
                    'js_instrumentation': {
                        'response': js_response, 
                        'link': 'next_link'
                    }
                }]
            })

            print("\nSubmitting username...")
            flow_data = self._execute_flow_task({
                'flow_token': flow_data['flow_token'],
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
            })

            print("\nSubmitting password...")
            flow_data = self._execute_flow_task({
                'flow_token': flow_data['flow_token'],
                'subtask_inputs': [{
                    'subtask_id': 'LoginEnterPassword', 
                    'enter_password': {
                        'password': password, 
                        'link': 'next_link'
                    }
                }]
            })

            # Process subtasks in a loop
            max_subtask_iterations = 10  # Safety limit
            iteration = 0
            
            while flow_data.get('subtasks') and iteration < max_subtask_iterations:
                iteration += 1
                subtask = flow_data['subtasks'][0]
                subtask_id = subtask['subtask_id']
                print(f"\nHandling subtask: {subtask_id} (iteration {iteration}/{max_subtask_iterations})")
                
                if subtask_id == 'DenyLoginSubtask':
                    error_message = subtask.get('errors', [{}])[0].get('message', 'Unknown error')
                    print(f"Login denied by Twitter: {error_message}")
                    return False

                elif subtask_id == 'LoginTwoFactorAuthChallenge':
                    if two_factor_secret:
                        print("Handling 2FA challenge...")
                        flow_data = self._handle_two_factor_auth(flow_data['flow_token'], two_factor_secret)
                    else:
                        print("2FA required but no secret provided. Exiting.")
                        return False
                        
                elif subtask_id == 'AccountDuplicationCheck':
                    print("Handling account duplication check...")
                    flow_data = self._execute_flow_task({
                        'flow_token': flow_data['flow_token'],
                        'subtask_inputs': [{
                            'subtask_id': 'AccountDuplicationCheck',
                            'check_logged_in_account': {
                                'link': 'AccountDuplicationCheck_false'
                            }
                        }]
                    })
                    
                elif subtask_id == 'LoginAcid':
                    if email:
                        print("Handling email verification...")
                        flow_data = self._execute_flow_task({
                            'flow_token': flow_data['flow_token'],
                            'subtask_inputs': [{
                                'subtask_id': 'LoginAcid', 
                                'enter_text': {
                                    'text': email, 
                                    'link': 'next_link'
                                }
                            }]
                        })
                    else:
                        print("Email verification required but no email provided. Exiting.")
                        return False
                        
                elif subtask_id == 'LoginSuccessSubtask':
                    self.username = username
                    print(f"Login successful for user: {username}")
                    
                    # Verify we're actually logged in by checking if we have the necessary cookies
                    if 'auth_token' in self.cookies and self.csrf_token:
                        print(f"Verified login. Auth token and CSRF token present.")
                        self.user_id = username  # Just use the provided username as the user ID
                    else:
                        print("Warning: Login appeared successful but auth tokens are missing")
                        
                    return True
                    
                else:
                    print(f"Unhandled subtask: {subtask_id}")
                    print(f"Subtask data: {json.dumps(subtask, indent=2)}")
                    return False

            if iteration >= max_subtask_iterations:
                print(f"Exceeded maximum subtask iterations ({max_subtask_iterations}). Exiting.")
                return False
                
            return False

        except Exception as e:
            print(f"Login failed with error: {e}")
            return False

    def create_tweet(self, text: str) -> Dict:
        """Create a new tweet using Twitter GraphQL API."""
        if not self.csrf_token:
            raise TwitterError("Not authenticated. Please login first.")
        
        # Add a small random delay before posting (simulates typing/thinking)
        thinking_time = random.uniform(2.0, 5.0)
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
        tweet_headers = self.headers.copy()
        tweet_headers.update({
            'content-type': 'application/json',
            'x-twitter-auth-type': 'OAuth2Client',
            'x-csrf-token': self.csrf_token,
            'authorization': f'Bearer {self.BEARER_TOKEN}',
            'x-twitter-client-language': 'en',
            'referer': 'https://twitter.com/home',
            'origin': 'https://twitter.com',
            'x-twitter-active-user': 'yes',
            # Adding a unique transaction ID helps appear more like a real browser
            'x-client-transaction-id': f"{random.randint(100000, 999999)}_{int(time.time() * 1000)}"
        })
        
        # Add auth token from cookies if available
        if 'auth_token' in self.cookies:
            auth_token = self.cookies['auth_token']
            tweet_headers['cookie'] = f'auth_token={auth_token}; ct0={self.csrf_token}'
        
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
            response = self._make_request('POST', url, json=payload, headers=tweet_headers)
            result = response.json()
            
            print(f"Tweet creation response: {json.dumps(result, indent=2)}")
            
            # Add a small delay after tweeting
            time.sleep(random.uniform(1.0, 3.0))
            
            return result
        except Exception as e:
            print(f"Failed to create tweet: {e}")
            raise TwitterError(f"Failed to create tweet: {e}")

class TwitterError(Exception):
    """Exception for Twitter-related errors."""
    pass
