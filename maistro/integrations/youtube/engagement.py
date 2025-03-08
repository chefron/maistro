import os
import logging
import threading
import time
import io
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from dotenv import load_dotenv
from maistro.core.agent import MusicAgent
from maistro.core.llm.messages import MessageHistory
from maistro.core.persona.generator import generate_character_prompt

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
                        "http://localhost",
                        "http://localhost:8080/"
                    ],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=['https://www.googleapis.com/auth/youtube.force-ssl']
        )

        # Try to run the local server flow, but catch specific errors
        try:
            print("\nAttempting to start authentication flow...")
            # Use a higher port number which is less likely to be in use
            credentials = flow.run_local_server(port=8080, open_browser=True)
            print("Authentication successful!")
            return credentials.refresh_token
        except OSError as e:
            print(f"Error starting local server: {e}")
            # If the local server fails, fall back to manual entry
            print("\nFalling back to manual authentication.")
            print("Please manually copy the following URL to your browser:")
            auth_url, _ = flow.authorization_url(prompt='consent')
            print(auth_url)
            print("\nAfter authorizing, you'll be redirected to an error page.")
            print("Copy the 'code' parameter from the URL and paste it here:")
            code = input("Enter the authorization code: ")
            
            # Exchange the code for credentials
            flow.fetch_token(code=code)
            credentials = flow.credentials
            print("Authentication successful!")
            return credentials.refresh_token
    
    except Exception as e:
        logger.error(f"OAuth setup failed: {e}")
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

    def start(self, callback: Callable[[Dict], None], interval: int = 300) -> bool:
        """
        Start monitoring channel for new comments

        Args:
            callback: Function to call with new comments
            interval: Seconds between chunks (default 5 mintues)
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
    
    def create_youtube_prompt(self) -> str:
        """
        Create a YouTube-specific prompt using the character prompt
        
        Returns:
            Complete prompt string for YouTube comment interactions
        """
        # Get the base character prompt
        character_prompt, _ = generate_character_prompt(
            config=self.agent.config,
            artist_name=self.agent.artist_name,
            client=self.agent.client
        )
        
        # Add YouTube-specific instructions
        youtube_instructions = "\n\nCURRENT TASK: You're responding to a comment on your YouTube video (captions provided for context). Keep your response conversational, authentic to your character, and relatively brief. Engage with the fan in a way that feels natural and on-brand for you."
        
        complete_prompt = character_prompt + youtube_instructions
        return complete_prompt
        
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
        """Process a new comment and generate a response using a balanced memory approach"""
        try:
            logger.info(f"\nProcessing comment from {comment['author']}")
            logger.info(f"Comment: {comment['text']}")

            # Get video context from captions if available
            video_context = self.get_video_captions(comment['video_id'])

            # BALANCED APPROACH: First query memory with just the comment
            comment_memory_context, comment_results = self.agent.memory.get_relevant_context(
                query=comment['text'],
                n_results=3  # Get top 3 results for comment
            )
            
            # Then query with captions if available
            caption_memory_context = ""
            if video_context:
                caption_memory_context, caption_results = self.agent.memory.get_relevant_context(
                    query=video_context,
                    n_results=2  # Get top 2 results for captions
                )
            
            # Combine memory contexts, prioritizing comment-related memories
            combined_memory_context = comment_memory_context
            
            # Add unique caption context only if it exists and doesn't duplicate comment context
            if caption_memory_context:
                # Simple approach to avoid duplication - in production you might want more sophisticated deduplication
                if caption_memory_context not in combined_memory_context:
                    combined_memory_context += "\n\n" + caption_memory_context
                    
            # Create a new YouTube-specific prompt for this comment
            youtube_prompt = self.create_youtube_prompt()
            
            # Create a new message history for this specific comment
            message_history = MessageHistory(youtube_prompt)
            
            # Get current date and time
            current_datetime = datetime.now().strftime("%B %d, %Y at %I:%M %p")
            
            # Construct prompt for the specific comment
            prompt = f"""Responding to a YouTube comment:

    From: {comment['author']} (on {current_datetime})
    Comment: {comment['text']}"""

            if video_context:
                prompt += f"\n\nVideo context from captions: {video_context}"
            
            # Add the user message to history (with combined memory context)
            message_history.add_user_message(prompt, combined_memory_context)
            
            # Get response from LLM
            messages = message_history.get_messages()

            # Print messages for debugging
            print("\n========== ALL MESSAGES SENT TO LLM ==========")
            for idx, msg in enumerate(messages):
                print(f"Message {idx} ({msg['role']}):")
                print(msg['content'])
                print("---------------------------------------------")
            print("===============================================\n")

            response = self.agent.client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=1024,
                messages=messages
            )
            
            # Extract response text
            response_text = response.content[0].text
            
            # Print the agent's response prominently
            print("\n========== AGENT RESPONSE ==========")
            print(response_text)
            print("=====================================\n")
            
            # Post the response
            if post_comment_reply(comment['id'], response_text):
                logger.info(f"✅ Posted response successfully!")
            else:
                logger.error("Failed to post response")

        except Exception as e:
            logger.error(f"Error handling comment: {e}")
      
if __name__ == "__main__":
    # Example usage
    load_dotenv()
    
    print("\n=== YouTube Engagement Tool ===\n")
    
    # Check for existing OAuth credentials
    refresh_token = os.getenv('YOUTUBE_REFRESH_TOKEN')
    client_id = os.getenv('YOUTUBE_CLIENT_ID')
    client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("ERROR: Missing YouTube API credentials")
        print("Please set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in your .env file")
        exit(1)
    
    # If no refresh token, perform OAuth flow manually
    if not refresh_token:
        print("No refresh token found. Starting OAuth authorization flow...\n")
        
        try:
            # Create client config dictionary
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": ["http://localhost:8080", "http://localhost"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }
            
            # Create flow with this config and scopes
            flow = InstalledAppFlow.from_client_config(
                client_config,
                scopes=['https://www.googleapis.com/auth/youtube.force-ssl']
            )
            
            # Force requesting a refresh token by setting access_type to offline
            # and approval_prompt to force (to prompt even if previously authorized)
            flow.oauth2session.redirect_uri = 'http://localhost:8080/'
            
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                prompt='consent',  # Force re-consent even if previously approved
                include_granted_scopes='true'
            )
            
            print(f"Please visit this URL to authorize the application:\n{auth_url}\n")
            
            # Run local server with specific parameters
            credentials = flow.run_local_server(
                port=8080,
                open_browser=True,
                authorization_prompt_message="Please complete the authorization in your browser"
            )
            
            # Extract and display the refresh token
            refresh_token = credentials.refresh_token
            
            if refresh_token:
                print("\n=== OAuth SUCCESSFUL! ===")
                print(f"Refresh Token: {refresh_token}")
                print("\nIMPORTANT: Add this to your .env file as:")
                print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")
                print("=========================\n")
                
                # Set for current session
                os.environ['YOUTUBE_REFRESH_TOKEN'] = refresh_token
            else:
                print("ERROR: No refresh token received. This typically means:")
                print("1. The application was already authorized (try revoking access at https://myaccount.google.com/permissions)")
                print("2. There may be a bug in the OAuth flow implementation")
                exit(1)
                
        except Exception as e:
            print(f"OAuth Error: {str(e)}")
            print("\nTroubleshooting tips:")
            print("1. Ensure port 8080 is free (check with 'sudo lsof -i :8080')")
            print("2. Verify your client_id and client_secret are correct")
            print("3. Try revoking existing permissions at https://myaccount.google.com/permissions")
            exit(1)
    else:
        print(f"Using existing refresh token from .env file")
    
    # Create agent and start monitoring only if we have a refresh token
    if os.getenv('YOUTUBE_REFRESH_TOKEN'):
        try:
            print("\nInitializing Music Agent...")
            agent = MusicAgent("dolla-llama")  # Replace with appropriate artist name
            
            print("Setting up YouTube responder...")
            responder = AgentResponder(agent)
            
            print("Testing YouTube API connection...")
            channel_id = get_channel_id()
            if not channel_id:
                print("ERROR: Could not retrieve YouTube channel ID")
                print("This suggests an authentication issue with your token")
                exit(1)
            
            print(f"Successfully connected to YouTube channel: {channel_id}")
            
            # Start monitoring
            print("\nStarting comment monitor...")
            monitor = CommentMonitor()
            if monitor.start(responder.handle_comment):
                print("\nMonitoring started! Press Ctrl+C to stop...")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    monitor.stop()
                    print("\nMonitoring stopped!")
            else:
                print("\nFailed to start monitoring. Check logs for details.")
        except Exception as e:
            print(f"Error: {e}")