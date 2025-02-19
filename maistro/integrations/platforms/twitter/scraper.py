from typing import Dict, List, Optional, Any
import requests
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from http.cookies import SimpleCookie

class TwitterScraper:
    """Main scraper class for Twitter web interface"""

    def __init__(self):
        self.session = requests.Session()
        self.cookies = {}
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'Referer': 'https://twitter.com/',
            'Origin': 'https://twitter.com',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
        self.csrf_token = None
        self.guest_token = None
        self.user_id = None
        self.username = None

    def _update_cookies(self, response: requests.Response) -> None:
        """Update session cookies from response"""
        cookies = SimpleCookie()
        for cookie in response.headers.get('Set-Cookie', '').split(','):
            try:
                cookies.load(cookie)
                for key, morsel in cookies.item():
                    self.cookies[key] = morsel.value
            except Exception:
                continue

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make a request with proper headers and error handling"""
        if 'headers' in kwargs:
            kwargs['headers'].update(self.headers)
        else:
            kwargs['headers'] = self.headers.copy()

        if self.csrf_token:
            kwargs['headers']['x-csrf-token'] = self.csrf_token

        kwargs['cookies'] = self.cookies

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            self._update_cookies(response)
            return response
        except requests.RequestException as e:
            raise TwitterError(f"Request failed: {str(e)}")
        
    def _graphql_request(self, endpoint: str, variables: Dict, features: Optional[Dict] = None) -> Dict:
        """Make a GraphQL request"""
        if features is None:
            features = {
                'responsive_web_graphql_exclude_directive_enabled': True,
                'verified_phone_label_enabled': False,
                'creator_subscriptions_tweet_preview_api_enabled': True,
                'responsive_web_graphql_timeline_navigation_enabled': True,
                'responsive_web_graphql_skip_user_profile_image_extensions_enabled': False,
                'tweetypie_unmention_optimization_enabled': True,
                'responsive_web_edit_tweet_api_enabled': True,
                'graphql_is_translatable_rweb_tweet_is_translatable_enabled': True,
                'view_counts_everywhere_api_enabled': True,
                'longform_notetweets_consumption_enabled': True,
                'tweet_awards_web_tipping_enabled': False,
                'freedom_of_speech_not_reach_fetch_enabled': True,
                'standardized_nudges_misinfo': True,
                'longform_notetweets_rich_text_read_enabled': True,
                'responsive_web_enhance_cards_enabled': False
            }

        params = {
            'variables': json.dumps(variables),
            'features': json.dumps(features)
        }

        url = f"https://twitter.com/i/api/graphql/{endpoint}?{urlencode(params)}"
        response = self._make_request('GET', url)
        return response.json()
    
    def login(self, username: str, password: str, email: Optional[str] = None) -> bool:
        """Log in to Twitter"""
        # Start login flow
        flow_token = self._init_login_flow()

        # Handle JS instrumentation
        flow_token = self._handle_js_instrumentation(flow_token)

        # Enter username
        flow_token = self._handle_user_identifier(flow_token, username)

        # Handle password
        flow_token = self._handle_password(flow_token, password)

        # Handle account duplication check if needed
        flow_token = self._handle_account_duplication(flow_token)

        # Handle email verification if needed
        if email and self._needs_email_verification(flow_token):
            flow_token = self._handle_email_verification(flow_token, email)
        
        # Success check
        success = self._handle_login_success(flow_token)
        if success:
            self.username = username
            return True
        
        return False
    
    def _init_login_flow(self) -> str:
        """Initialize login flow and get first flow token"""
        flow_data = {
            'flow_name': 'login',
            'input_flow_data': {
                'flow_context': {
                    'debug_overrides': {},
                    'start_location': {
                        'location': 'splash_screen'
                    }
                }
            }
        }
        
        response = self._make_request(
            'POST', 
            'https://twitter.com/i/api/1.1/onboarding/task.json',
            json=flow_data
        )
        
        data = response.json()
        return data['flow_token']

    def _handle_js_instrumentation(self, flow_token: str) -> str:
        """Handle JS instrumentation subtask"""
        subtask_data = {
            'flow_token': flow_token,
            'subtask_inputs': [{
                'subtask_id': 'LoginJsInstrumentationSubtask',
                'js_instrumentation': {
                    'response': '{}',
                    'link': 'next_link'
                }
            }]
        }
        
        response = self._make_request(
            'POST',
            'https://twitter.com/i/api/1.1/onboarding/task.json',
            json=subtask_data
        )
        
        data = response.json()
        return data['flow_token']

    def _handle_user_identifier(self, flow_token: str, username: str) -> str:
        """Handle username entry subtask"""
        subtask_data = {
            'flow_token': flow_token,
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
        }
        
        response = self._make_request(
            'POST',
            'https://twitter.com/i/api/1.1/onboarding/task.json',
            json=subtask_data
        )
        
        data = response.json()
        return data['flow_token']

    def _handle_password(self, flow_token: str, password: str) -> str:
        """Handle password entry subtask"""
        subtask_data = {
            'flow_token': flow_token,
            'subtask_inputs': [{
                'subtask_id': 'LoginEnterPassword',
                'enter_password': {
                    'password': password,
                    'link': 'next_link'
                }
            }]
        }
        
        response = self._make_request(
            'POST',
            'https://twitter.com/i/api/1.1/onboarding/task.json',
            json=subtask_data
        )
        
        data = response.json()
        return data['flow_token']

    def _handle_account_duplication(self, flow_token: str) -> str:
        """Handle account duplication check if needed"""
        subtask_data = {
            'flow_token': flow_token,
            'subtask_inputs': [{
                'subtask_id': 'AccountDuplicationCheck',
                'check_logged_in_account': {
                    'link': 'AccountDuplicationCheck_false'
                }
            }]
        }
        
        response = self._make_request(
            'POST',
            'https://twitter.com/i/api/1.1/onboarding/task.json',
            json=subtask_data
        )
        
        data = response.json()
        return data['flow_token']

    def _needs_email_verification(self, flow_token: str) -> bool:
        """Check if email verification is needed"""
        try:
            response = self._make_request(
                'GET',
                f'https://twitter.com/i/api/1.1/onboarding/task.json?flow_token={flow_token}'
            )
            data = response.json()
            return any(
                subtask['subtask_id'] == 'LoginAcid'
                for subtask in data.get('subtasks', [])
            )
        except Exception:
            return False

    def _handle_email_verification(self, flow_token: str, email: str) -> str:
        """Handle email verification if needed"""
        subtask_data = {
            'flow_token': flow_token,
            'subtask_inputs': [{
                'subtask_id': 'LoginAcid',
                'enter_text': {
                    'text': email,
                    'link': 'next_link'
                }
            }]
        }
        
        response = self._make_request(
            'POST',
            'https://twitter.com/i/api/1.1/onboarding/task.json',
            json=subtask_data
        )
        
        data = response.json()
        return data['flow_token']

    def _handle_login_success(self, flow_token: str) -> bool:
        """Handle final login success check"""
        subtask_data = {
            'flow_token': flow_token,
            'subtask_inputs': []
        }
        
        try:
            response = self._make_request(
                'POST',
                'https://twitter.com/i/api/1.1/onboarding/task.json',
                json=subtask_data
            )
            
            data = response.json()
            return 'errors' not in data
            
        except TwitterError:
            return False
    
    def post_tweet(self, text: str, reply_to: Optional[str] = None) -> Dict:
        """Post a new tweet"""
        variables = {
            'tweet_text': text,
            'dark_request': False,
            'media': {
                'media_entities': [],
                'possibly_sensitive': False
            },
            'semantic_annotation_ids': []
        }

        if reply_to:
            variables['reply'] = {'in_reply_to_tweet_id': reply_to}

        return self._graphql_request('a1p9RWpkYKBjWv_I3WzS-A/CreateTweet', variables)

class TwitterError(Exception):
    """Base exception for Twitter errors"""
    pass




    

            

