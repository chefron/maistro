import os
import logging
import threading
import time
import io
from typing import Dict, List, Optional, Callable, Any
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from dotenv import load_dotenv
from maistro.core.agent import MusicAgent

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
                        print(f"Found {len(new_comments)} unprocessed comments")
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
        
class AgentResponder:
    """Manages agent-based automatic responses to YouTube comments"""

    def __init__(self, agent):
        self.agent = agent
        self.monitor = CommentMonitor()
        
    def get_video_captions(self, video_id: str) -> Optional[str]:
        """Get captions for a video to provide context"""
        try:
            youtube = get_oauth_client()
            if not youtube:
                return None
            
            captions_text = None

            # Retrieve captions list
            captions_response = youtube.captions().list(
                part="id",
                videoId=video_id
            ).execute()

            # Check if captions exist
            if 'items' in captions_response and captions_response['items']:
                caption_id = captions_response['items'][0]['id']  # Get the first caption track
                print(f"Found Caption ID: {caption_id}")

                # Download captions using MediaIoBaseDownload
                request = youtube.captions().download(id=caption_id, tfmt='srt')
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)

                done = False
                while not done:
                    _, done = downloader.next_chunk()

                captions_text = fh.getvalue().decode("utf-8")  # Decode bytes to string
                print(captions_text)

                return self._clean_captions(captions_text)

            else:
                print(f"No captions found for video {video_id}")

            return self._clean_captions(captions_text)
        
        except Exception as e:
            logger.error(f"Failed to get captions for video {video_id}: {e}")
            return None
        
    def _clean_captions(self, captions: str) -> str:
        """Extract readable text from SRT formatted captions.
        
        SRT format looks like:
            1
            00:00:01,000 --> 00:00:04,000
            This is the actual caption text
            
            2
            00:00:05,000 --> 00:00:09,000
            More caption text here
        """
        if not captions:
            return None
        
        try:
            print("\nRaw captions:")
            print(captions)

            subtitle_lines = []
            for line in captions.split('\n'):
                line = line.strip()
                # Skip if line is:
                # - A timestamp (contains -->)
                is_timestamp = '-->' in line
                # - A subtitle number (just digits)
                is_subtitle_number = line.isdigit()
                # - Empty
                is_empty = not line
                
                if not (is_timestamp or is_subtitle_number or is_empty):
                    subtitle_lines.append(line)
            return ' '.join(subtitle_lines)
        
        except Exception as e:
            logger.error(f"Failed to clean captions: {e}")
            return None

    def handle_comment(self, comment: Dict[str, Any]) -> None:
        """Process a new comment and generate a response"""
        try:
            logger.info(f"\nProcessing comment from {comment['author']}")
            logger.info(f"Comment: {comment['text']}")

            # Get video context from captions if available
            context = self.get_video_captions(comment['video_id'])

            if context:
                print("Cleaned video captions:")
                print(context)
            else:
                print("No captions available for this video.")

            context_msg = f"\nVideo context: {context}" if context else "\nNo video context available"

            # Construct prompt for the agent
            prompt = f"""Please help me respond to this YouTube comment:

From: {comment['author']}
Comment: {comment['text']}
Video captions: {context_msg}

Please write a concise response to the comment. If video captions are provided, you can use them for context, but don't feel obligated to do so."""

            # Generate response using the agent
            response = self.agent.chat(prompt)

            # Post the response
            if post_comment_reply(comment['id'], response):
                logger.info(f"✅ Posted response: {response}")
            else:
                logger.error("Failed to post response")

        except Exception as e:
            logger.error(f"Error handling comment: {e}")
      
if __name__ == "__main__":
    # Example usage
    load_dotenv()

    agent = MusicAgent("dolla-llama")  # Replace with the appropriate artist name
    responder = AgentResponder(agent)

    # Start monitoring
    monitor = CommentMonitor()
    if monitor.start(responder.handle_comment):
        print("\nMonitoring started! Press Ctrl+C to stop...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            monitor.stop()
            print("\nMonitoring stopped!")