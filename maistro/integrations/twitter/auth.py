from typing import Dict, Optional, Any, List, Tuple
import requests
import json
import time
import random
import ssl
import socket
import os
import pickle
import uuid
from http.cookies import SimpleCookie
from datetime import datetime
import pyotp
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from utils import RequestQueue, TwitterError

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

class TwitterAuth:
    """Enhanced Twitter login with improved session handling and flow"""

    BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
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
    
    # Mobile user agents that have better success with Twitter login
    MOBILE_USER_AGENTS = [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 11; Nokia G20) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.88 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 12; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.6099.119 Mobile/15E148 Safari/604.1',
    ]

    def __init__(self):
        print("\nInitializing TwitterAuth...")
        self.session = requests.Session()
        
        # Install the TLS cipher randomizing adapter and disable SSL verification for testing
        self.session.mount('https://', TLSCipherRandomizingAdapter())
        self.session.verify = False
        # Suppress InsecureRequestWarning
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.cookies = {}

        self.user_agent = random.choice(self.MOBILE_USER_AGENTS)
        print(f"Using User-Agent: {self.user_agent}")

        # Create client UUID that stays consistent across requests
        import uuid
        self.client_uuid = str(uuid.uuid4())
        print(f"Generated client UUID: {self.client_uuid}")
        
        # Create a directory for cookie cache if it doesn't exist
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        
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
            'x-client-uuid': self.client_uuid,
        }

        self.csrf_token = None
        print("Getting guest token...")
        self.guest_token = self._get_guest_token()
        self.headers['x-guest-token'] = self.guest_token
        self.user_id = None
        self.username = None
        
        # Add some randomized delays between requests
        self.min_delay = 2.0
        self.max_delay = 5.0

        # Create request queue for rate-limiting requests
        self.request_queue = RequestQueue()

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

                guest_token_headers = {
                    'authorization': f'Bearer {self.BEARER_TOKEN}',
                    'User-Agent': self.user_agent,
                    'content-type': 'application/json',
                    'Accept': '*/*',
                }

                response = self.session.post(
                    self.GUEST_TOKEN_URL, 
                    headers=guest_token_headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    token = response.json().get("guest_token", "")
                    if not token:
                        print("Warning: Received empty guest token, retrying...")
                        continue
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
    
    def _parse_cookie_date(self, date_str):
        """Parse different date formats in cookies."""
        formats = [
            '%a, %d %b %Y %H:%M:%S GMT',  # Standard format
            '%a, %d-%b-%y %H:%M:%S GMT',  # Twitter mobile format
            '%a, %d-%b-%Y %H:%M:%S GMT',  # Another variation
            '%a, %d %b %y %H:%M:%S GMT'   # Short year format
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).timestamp()
            except ValueError:
                continue
        
        print(f"Could not parse date: {date_str}")
        return None

    def _update_cookies(self, response: requests.Response) -> None:
        """Extract and store session cookies with all attributes."""
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
            # Try to parse the entire header
            try:
                cookies.load(cookie_header)
                for key, morsel in cookies.items():
                    self.cookies[key] = morsel.value
                    
                    # Preserve all cookie attributes when setting in session
                    domain = morsel['domain'] if 'domain' in morsel else '.twitter.com'
                    path = morsel['path'] if 'path' in morsel else '/'
                    # Manually parse the 'expires' attribute
                    expires = None
                    if 'expires' in morsel:
                        expires = self._parse_cookie_date(morsel['expires'])
                    
                    self.session.cookies.set(
                        key, 
                        morsel.value,
                        domain=domain,
                        path=path,
                        expires=expires
                    )
                    
                    if key == 'ct0':  # CSRF token
                        self.csrf_token = morsel.value
                        print(f"Found CSRF token from header: {morsel.value[:5]}...")
            except Exception as e:
                # If that fails, try splitting by comma and parsing each part
                print(f"Error processing cookie header as a whole: {e}")
                for cookie in cookie_header.split(','):
                    try:
                        single_cookie = SimpleCookie()
                        single_cookie.load(cookie)
                        for key, morsel in single_cookie.items():
                            self.cookies[key] = morsel.value
                            self.session.cookies.set(key, morsel.value, domain='.twitter.com', path='/')
                            if key == 'ct0':  # CSRF token
                                self.csrf_token = morsel.value
                                print(f"Found CSRF token from header: {morsel.value[:5]}...")
                    except Exception as e:
                        print(f"Error processing cookie part: {e}")
                        continue
                    
        print(f"Current cookie count: {len(self.cookies)}")

    def make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Handle request execution with error handling and queue management."""
        print(f"\nQueuing {method} request to {url}")
        
        # Define the actual request function
        def execute_request():
            print(f"Executing {method} request to {url}")
            
            # Prepare request headers
            request_headers = self.headers.copy()
            if self.csrf_token:
                request_headers['x-csrf-token'] = self.csrf_token

            # Update x-client-transaction-id for each request
            import base64
            import os
            transaction_id_bytes = os.urandom(48)
            transaction_id = base64.b64encode(transaction_id_bytes).decode('utf-8')
            transaction_id = transaction_id.replace('+', '').replace('/', '')[:72]
            request_headers['x-client-transaction-id'] = transaction_id
            
            kwargs.setdefault('headers', request_headers)
            kwargs.setdefault('cookies', self.cookies)
            kwargs.setdefault('timeout', 15)  # Set a reasonable timeout
            
            response = self.session.request(method, url, **kwargs)
            print(f"Response status code: {response.status_code}")
            self._update_cookies(response)

            # Handle different status codes
            if response.status_code == 403:  # Forbidden, likely means guest token expired
                print("403 Forbidden - Refreshing guest token...")
                self.guest_token = self._get_guest_token()
                self.headers['x-guest-token'] = self.guest_token
                raise Exception("Guest token expired, please retry request")
                
            elif response.status_code == 429:  # Rate limited
                retry_after = int(response.headers.get('retry-after', 60))
                print(f"Rate limited. Waiting for {retry_after} seconds...")
                time.sleep(retry_after)
                raise Exception(f"Rate limited, retry after {retry_after} seconds")
                
            response.raise_for_status()
            return response
        
        # Use the request queue to manage this request
        return self.request_queue.add(execute_request)

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
            
        response = self.make_request('POST', self.LOGIN_URL, json=data)
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

    def _get_cookie_cache_path(self, username: str) -> str:
        """Get the path to the cookie cache file for a specific username."""
        return os.path.join(self.cache_dir, f"{username}_cookies.pkl")
    
    def _save_cookies_to_cache(self, username: str) -> None:
        """Save the current cookies to a cache file with full metadata."""
        try:
            cache_path = self._get_cookie_cache_path(username)
            
            # Extract full cookie objects from the session with all attributes
            cookie_objects = []
            for cookie in self.session.cookies:
                cookie_obj = {
                    'key': cookie.name,
                    'value': cookie.value,
                    'domain': cookie.domain,
                    'path': cookie.path,
                    'secure': cookie.secure,
                    'httpOnly': cookie.has_nonstandard_attr('HttpOnly'),
                    'sameSite': cookie.get_nonstandard_attr('SameSite', 'Lax')
                }
                cookie_objects.append(cookie_obj)
            
            cookie_data = {
                'cookies': cookie_objects,  # Store full cookie objects
                'cookies_dict': self.cookies,  # Also store the simple dict for backward compatibility
                'csrf_token': self.csrf_token,
                'timestamp': time.time()
            }
            
            with open(cache_path, 'wb') as f:
                pickle.dump(cookie_data, f)
            print(f"Saved {len(cookie_objects)} cookies to cache for user: {username}")
        except Exception as e:
            print(f"Error saving cookies to cache: {e}")
    
    def _load_cookies_from_cache(self, username: str) -> bool:
        """Load cookies from cache file if available and not expired."""
        try:
            cache_path = self._get_cookie_cache_path(username)
            if not os.path.exists(cache_path):
                return False
                
            with open(cache_path, 'rb') as f:
                cookie_data = pickle.load(f)
                
            # Check if cookies are expired (older than 12 hours)
            if time.time() - cookie_data.get('timestamp', 0) > 12 * 60 * 60:
                print("Cached cookies are expired")
                return False
            
            # Handle both new format (with full cookie objects) and old format
            if 'cookies_dict' in cookie_data:
                # New format with full cookie metadata
                self.cookies = cookie_data.get('cookies_dict', {})
                cookie_objects = cookie_data.get('cookies', [])
                
                # Clear existing session cookies
                self.session.cookies.clear()
                
                # Set cookies with full metadata
                for cookie_obj in cookie_objects:
                    self.session.cookies.set(
                        cookie_obj['key'], 
                        cookie_obj['value'],
                        domain=cookie_obj['domain'],
                        path=cookie_obj['path'],
                        secure=cookie_obj['secure']
                    )
                    
                print(f"Loaded {len(cookie_objects)} cookies with full metadata")
            else:
                # Old format with simple dict
                self.cookies = cookie_data.get('cookies', {})
                
                # Update session cookies with basic attributes
                for name, value in self.cookies.items():
                    self.session.cookies.set(name, value, domain='.twitter.com', path='/')
            
            self.csrf_token = cookie_data.get('csrf_token')
                
            print(f"Loaded cookies from cache for user: {username}")
            print(f"Cookie count: {len(self.cookies)}")
            return len(self.cookies) > 0 and 'auth_token' in self.cookies and self.csrf_token is not None
        except Exception as e:
            print(f"Error loading cookies from cache: {e}")
            return False
    
    def _verify_credentials(self) -> bool:
        """Verify if the current credentials are valid"""
        try:
            # Check if we have the essential cookies
            essential_cookies = ['auth_token', 'ct0', 'twid']
            
            for cookie in essential_cookies:
                if cookie not in self.cookies:
                    print(f"Missing essential cookie: {cookie}")
                    return False
            
            # If we have all essential cookies and they're not empty, assume they're valid
            print("All essential cookies present, assuming valid session")
            return True
        except Exception as e:
            print(f"Error verifying credentials: {e}")
            return False
    
    def login(self, username: str, password: str, email: Optional[str] = None, two_factor_secret: Optional[str] = None) -> bool:
        """Log in to Twitter and handle the flow."""
        print(f"\nStarting login process for user: {username}")
        print(f"Email provided: {'Yes' if email else 'No'}")
        print(f"2FA secret provided: {'Yes' if two_factor_secret else 'No'}")
        
        # Try to use cached cookies first
        if self._load_cookies_from_cache(username):
            print("Using cached cookies to verify login")
            if self._verify_credentials():
                print("Successfully logged in using cached cookies")
                self.username = username
                return True
            else:
                print("Cached cookies are invalid, proceeding with full login")
        
        # Clear cookies before login to avoid conflicts
        self.session.cookies.clear()
        self.cookies = {}
        
        # Always use a mobile user agent for login
        self.user_agent = random.choice(self.MOBILE_USER_AGENTS)
        self.headers['User-Agent'] = self.user_agent
        print(f"Using mobile User-Agent for login: {self.user_agent}")
        
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
                        
                        # Save cookies to cache for future use
                        self._save_cookies_to_cache(username)
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

    def login_with_retry(self, username, password, email=None, two_factor_secret=None, max_attempts=2, retry_delay=7.0):
        """Login with automatic retry on failure"""

        # Add a pre-login delay to appear more human-like
        human_delay = random.uniform(4.0, 7.0)
        print(f"Adding pre-login delay of {human_delay:.2f} seconds...")
        time.sleep(human_delay)
        
        # Try an initial warmup request to establish some cookies
        try:
            print("Performing warm-up request...")
            # Use a more reliable URL that doesn't require authentication
            self.make_request('GET', 'https://twitter.com/robots.txt')
        except Exception as e:
            print(f"Warm-up request failed (continuing anyway): {e}")
            # Add a small delay before proceeding with the login
            time.sleep(2)
        
        # Try login multiple times
        for attempt in range(1, max_attempts + 1):
            print(f"\nLogin attempt {attempt}/{max_attempts}...")
            
            success = self.login(username, password, email, two_factor_secret)
            
            if success:
                print(f"Login successful on attempt {attempt}")
                return True
                
            if attempt < max_attempts:
                # Add a human-like delay between attempts
                delay = retry_delay * (1 + random.random() * 0.5)  # Add some randomness
                print(f"Login attempt {attempt} failed. Waiting {delay:.2f} seconds before retry...")
                time.sleep(delay)
                
                # Important: Don't clear cookies or reset session between attempts
                
        return False