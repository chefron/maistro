import os
import logging
import threading
import time
from typing import Dict, List, Optional, Callable
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('maistro.integrations.youtube.engagement')

def setup_oauth(client_id: str, client_secret: str) -> Optional[str]:
    """Set up OAuth 2 credentials for posting comments"""
    try:
        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": [
                        "http://localhost:8080",
                        "http://localhost"
                    ],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=['https://www.googleapis.com/auth/youtube.force-ssl']
        )

        credentials = flow.run_local_server(port=8080, open_browser=True)
        return credentials.refresh_token
    
    except Exception as e:
        logger.error(f"Oauth setup failed: {e}")
        return None
    
def get_oauth_client() -> Optional[object]:
    """Get authenticated YouTube client using OAuth credentials"""
    try: 
        client_id = os.getenv('YOUTUBE_CLIENT_ID')
        client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
        refresh_token = os.getenv('YOUTUBE_REFRESH_TOKEN')

        if not all([client_id, client_secret, refresh_token]):
            logger.error("Missing Oauth credentials")
            return None
        
        credentials = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=['https://www.googleapis.com/auth/youtube.force-ssl']
        )
        
        if not credentials.valid:
            credentials.refresh(Request())

        return build('youtube', 'v3', credentials=credentials)
    
    except Exception as e:
        logger.error(f"Failed to get Oauth client: {e}")
        return None
    
def get_channel_id() -> Optional[str]:
    """Get the authenticated channel's ID"""
    try:
        youtube = get_oauth_client()
        if not youtube:
            return None
        
        response = youtube.channels().list(
            part='id',
            mine=True
        ).execute()

        if response.get('items'):
            return response['items'][0]['id']
        return None
    
    except Exception as e:
        logger.error(f"Failed to get channel ID: {e}")
        return None

def get_recent_comments(channel_id: str, count: int = 100) ->List[Dict]:
    """Get recent comments from all videos on a channel"""
    try:
        youtube = get_oauth_client()
        if not youtube:
            return []
        
        # Fetch comments page by page until we have enough or run out
        comments = []
        next_page_token = None

        while len(comments) < count:
            response = youtube.commentThreads().list(
                part='snippet,replies',
                allThreadsRelatedToChannelId=channel_id,
                maxResults=min(100, count - len(comments)),
                pageToken=next_page_token,
                order='time',
            ).execute()

            for item in response.get('items', []):
                comment = item['snippet']['topLevelComment']
                comment_author_id = comment['snippet']['authorChannelId']['value']

                # Skip comments from the channel owner
                if comment_author_id == channel_id:
                    continue

                # Check if bot has already replied
                has_bot_reply = False
                if 'replies' in item:
                    has_bot_reply = any(
                        reply['snippet']['authorChannelId']['value'] == channel_id
                        for reply in item['replies']['comments']
                    )

                if not has_bot_reply:
                    comment_data = {
                        'id': item['id'],
                        'text': comment['snippet']['textDisplay'],
                        'author': comment['snippet']['authorDisplayName'],
                        'video_id': item['snippet']['videoId'],
                        'published_at': comment['snippet']['publishedAt'],
                        'like_count': comment['snippet']['likeCount'],
                    }
                    comments.append(comment_data)
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token or len(comments) >= count:
                break

        return comments [:count]
    
    except Exception as e:
        logger.error(f"Failed to get comments: {e}")
        return []
    
def post_comment_reply(comment_id: str, reply_text: str) -> bool:
    """Post a reply to a YouTube comment"""
    try:
        youtube = get_oauth_client()
        if not youtube:
            return False
        
        youtube.comments().insert(
            part='snippet',
            body={
                'snippet': {
                    'parentId': comment_id,
                    'textOriginal': reply_text
                }
            }
        ).execute()

        return True
    
    except Exception as e:
        logger.error(f"Failed to post reply: {e}")
        return False
            
class CommentMonitor:
    """Monitors YouTube channel for new comments"""

    def __init__(self): 
        self._polling_thread = None
        self._running = False
        self._processed_comments = set()

    def initialize_oauth(self) -> bool:
        """Set up OAuth credentials if needed"""
        if not os.getenv('YOUTUBE_REFRESH_TOKEN'):
            logger.info("No refresh token found - performing initial OAuth setup...")
            client_id = os.getenv('YOUTUBE_CLIENT_ID')
            client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
            
            if not client_id or not client_secret:
                logger.error("Please set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in your .env file")
                return False
                
            refresh_token = setup_oauth(client_id, client_secret)
            if refresh_token:
                logger.info(f"Got refresh token: {refresh_token}")
                logger.info("Please add this to your .env file as YOUTUBE_REFRESH_TOKEN=<token>")
                return False
            else:
                logger.error("Failed to get refresh token")
                return False
        return True

    def start(self, callback: Callable[[Dict], None], interval: int = 60) -> bool:
        """
        Start monitoring channel for new comments

        Args:
            callback: Function to call with new comments
            interval: Seconds between chunks (default 60)
        """

        if self._running:
            logger.info("Monitor is already running")
            return False
        
        channel_id = get_channel_id()
        if not channel_id:
            logger.error("Could not get channel ID")
            return False

        def poll_comments():
            while self._running:
                try: 
                    logger.info("Checking for new YouTube comments")
                    comments = get_recent_comments(channel_id)

                    # Filter for comments we haven't processed yet
                    new_comments = [
                        comment for comment in comments
                        if comment['id'] not in self._processed_comments
                    ]

                    if new_comments:
                        logger.info(f"Found {len(new_comments)} unprocessed comments")
                        for comment in new_comments:
                            try:
                                callback(comment)
                                self._processed_comments.add(comment['id'])
                            except Exception as e:
                                logger.error(f"Error in comment callback: {e}")

                    else:
                        print("No new comments since last check")  # Add this

                    print(f"Waiting {interval} seconds before next check...")
                    time.sleep(interval)
                
                except Exception as e:
                    logger.error(f"Error in comment polling: {e}")
                    time.sleep(interval)

        try:
            self._running = True
            self._polling_thread = threading.Thread(target=poll_comments, daemon=True)
            self._polling_thread.start()
            logger.info("Started YouTube comment monitoring")
            return True
        
        except Exception as e:
            self._running = False
            logger.error(f"Failed to start monitoring: {e}")
            return False
    
    def stop(self) -> bool:
        "Stop monitoring for new comments"
        if not self._running:
            logger.info("Monitor is not running")
            return False

        try:
            self._running = False
            self._polling_thread = None
            logger.info("Stopped YouTube comment monitoring")
            return True
        
        except Exception as e:
            logger.error(f"Error stopping monitoring: {e}")
            return False
        
if __name__ == "__main__":
    # Example usage
    load_dotenv()

    def handle_comment(comment):
        print(f"\nNew comment from {comment['author']}:")
        print(f"Text: {comment['text']}")
        print(f"Video: {comment['video_id']}")

        # Example auto-reply
        reply = f"Thanks for your comment, {comment['author']}!"
        if post_comment_reply(comment['id'], reply):
            print("Reply posted successfully!")
        else:
            print("Failed to post reply")

    # Start monitoring
    monitor = CommentMonitor()
    if monitor.start(handle_comment):
        print("\nMonitoring started! Press Crtl+C to stop...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            monitor.stop()
            print("\nMonitoring stopped!")