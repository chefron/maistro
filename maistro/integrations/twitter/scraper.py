from typing import Dict, List, Optional, Any
import requests
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from http.cookies import SimpleCookie

import pyotp
from time import sleep

class TwitterScraper:
    """Main scraper class for Twitter web interface"""

    BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

    def __init__(self):
        self.session = requests.Session()
        # Configure to use Tor's SOCKS proxy
        self.session.proxies = {
            'http': 'socks5h://localhost:9050',
            'https': 'socks5h://localhost:9050'
        }
        self.cookies = {}
        self.headers = {
            'authorization': f'Bearer {self.BEARER_TOKEN}',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Nokia G20) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.88 Mobile Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'x-twitter-auth-type': 'OAuth2Client',
            'x-twitter-active-user': 'yes',
            'x-twitter-client-language': 'en',
        }
        self.csrf_token = None
        self.guest_token = None
        self.user_id = None
        self.username = None

    def _handle_two_factor_challenge(self, flow_token: str, two_factor_secret: str) -> Dict:
        """Handle 2FA challenge using TOTP"""
        totp = pyotp.TOTP(two_factor_secret)
        last_error = None

        # Try a few times to handle clock skew
        for attempt in range(3):
            try:
                if attempt > 0:
                    print(f"2FA attempt {attempt + 1}")
                    sleep(2 * attempt)  # Exponential backoff

                code = totp.now()
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
            except TwitterError as e:
                print(f"2FA attempt failed: {str(e)}")
                last_error = e

        if last_error:
            raise last_error
        return None

    def _reset_cookies(self):
        """Reset session-related cookies that Twitter checks"""
        cookies_to_remove = [
            'twitter_ads_id',
            'ads_prefs',
            '_twitter_sess',
            'zipbox_forms_auth_token',
            'lang',
            'bouncer_reset_cookie',
            'twid',
            'twitter_ads_idb',
            'email_uid',
            'external_referer',
            'ct0',
            'aa_u'
        ]
        self.cookies = {k: v for k, v in self.cookies.items() 
                       if k not in cookies_to_remove}

    def _update_cookies(self, response: requests.Response) -> None:
        """Update session cookies from response"""
        cookies = SimpleCookie()
        for cookie in response.headers.get('Set-Cookie', '').split(','):
            try:
                cookies.load(cookie)
                for key, morsel in cookies.items():
                    self.cookies[key] = morsel.value
                    # Update csrf token if present
                    if key == 'ct0':
                        self.csrf_token = morsel.value
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

        print(f"Making {method} request to {url}")
        print(f"Headers: {kwargs['headers']}")
        print(f"Cookies: {kwargs['cookies']}")
        if 'json' in kwargs:
            print(f"JSON Payload: {kwargs['json']}")

        try:
            response = self.session.request(method, url, **kwargs)
            print(f"Response Status Code: {response.status_code}")
            print(f"Response Headers: {response.headers}")
            
            # Try to print response body for debugging
            try:
                print(f"Response Body: {response.text}")
            except:
                pass
                
            response.raise_for_status()
            self._update_cookies(response)
            return response
            
        except requests.RequestException as e:
            print(f"Request Exception: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response Body: {e.response.text}")
            raise TwitterError(f"Request failed: {str(e)}")

    def _execute_flow_task(self, data: Dict) -> Dict:
        """Execute a flow task and handle the response properly"""
        if not self.guest_token:
            raise TwitterError("No guest token available")

        response = self._make_request(
            'POST',
            'https://api.twitter.com/1.1/onboarding/task.json',
            json=data
        )

        flow_data = response.json()

        # Check for errors
        if 'errors' in flow_data and flow_data['errors']:
            error = flow_data['errors'][0]
            raise TwitterError(f"Flow error ({error.get('code')}): {error.get('message')}")

        # Ensure we have a flow token
        if not flow_data.get('flow_token'):
            raise TwitterError("No flow token in response")

        return flow_data

    def _get_guest_token(self) -> str:
        """Get guest token required for requests"""
        response = self.session.post(
            'https://api.twitter.com/1.1/guest/activate.json',
            headers=self.headers
        )
        if response.status_code != 200:
            raise TwitterError("Failed to get guest token")
            
        data = response.json()
        return data['guest_token']

    def login(self, username: str, password: str, email: Optional[str] = None, two_factor_secret: Optional[str] = None) -> bool:
        """Log in to Twitter"""
        # Reset cookies and get guest token
        self._reset_cookies()
        self.guest_token = self._get_guest_token()
        self.headers['x-guest-token'] = self.guest_token

        try:
            # Initialize login flow
            flow_data = self._execute_flow_task({
                'flow_name': 'login',
                'input_flow_data': {
                    'flow_context': {
                        'debug_overrides': {},
                        'start_location': {
                            'location': 'splash_screen'
                        }
                    }
                }
            })

            # Handle JS instrumentation
            flow_data = self._execute_flow_task({
                'flow_token': flow_data['flow_token'],
                'subtask_inputs': [{
                    'subtask_id': 'LoginJsInstrumentationSubtask',
                    'js_instrumentation': {
                        'response': '{}',
                        'link': 'next_link'
                    }
                }]
            })

            # Enter username
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

            # Enter password
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

            # Check next steps from the response
            while flow_data.get('subtasks'):
                subtask = flow_data['subtasks'][0]
                subtask_id = subtask['subtask_id']
                print(f"Processing subtask: {subtask_id}")

                # Exit immediately if login is denied
                if subtask_id == 'DenyLoginSubtask':
                    error_msg = subtask.get('cta', {}).get('secondary_text', {}).get('text', 'Login denied')
                    print(f"Login denied: {error_msg}")
                    return False

                # Otherwise continue with normal flow
                if subtask_id == 'LoginSuccessSubtask':
                    flow_data = self._execute_flow_task({
                        'flow_token': flow_data['flow_token'],
                        'subtask_inputs': []
                    })
                    self.username = username
                    return True

                elif subtask_id == 'LoginAcid' and email:
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

                elif subtask_id == 'AccountDuplicationCheck':
                    flow_data = self._execute_flow_task({
                        'flow_token': flow_data['flow_token'],
                        'subtask_inputs': [{
                            'subtask_id': 'AccountDuplicationCheck',
                            'check_logged_in_account': {
                                'link': 'AccountDuplicationCheck_false'
                            }
                        }]
                    })
                
                elif subtask_id == 'LoginTwoFactorAuthChallenge':
                    if not two_factor_secret:
                        print("Two-factor authentication required but no secret provided")
                        return False
                    flow_data = self._handle_two_factor_challenge(flow_data['flow_token'], two_factor_secret)

                elif subtask_id == 'LoginEnterPassword':
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

                else:
                    print(f"Unexpected subtask: {subtask_id}")
                    print(f"Full subtask data: {subtask}")
                    return False

            return False

        except TwitterError as e:
            print(f"Login error: {str(e)}")
            return False

class TwitterError(Exception):
    """Base exception for Twitter errors"""
    pass