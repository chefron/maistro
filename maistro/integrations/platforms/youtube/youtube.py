from datetime import datetime, timezone
import os
from typing import Dict, List, Optional
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

def get_youtube_channel_stats(channel_id: str, api_key: Optional[str] = None) -> Optional[Dict]:
    """Fetch basic statistics for a YouTube channel"""
    api_key = api_key or os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        raise ValueError("YouTube API key is required")
    
    youtube = build('youtube', 'v3', developerKey=api_key)

    try:
        # Get channel statistics
        channel_response = youtube.channels().list(
            part='snippet,statistics',
            id=channel_id
        ).execute()

        if not channel_response['items']:
            return None
        
        channel_data = channel_response['items'][0]
        return {
            'channel_name': channel_data['snippet']['title'],
            'description': channel_data['snippet']['description'],
            'subscriber_count': int(channel_data['statistics']['subscriberCount']),
            'video_count': int(channel_data['statistics']['videoCount']),
            'view_count': int(channel_data['statistics']['viewCount']),
            'created_at': channel_data['snippet']['publishedAt']
        }
    
    except HttpError as e:
        print (f"Error fetching channel stats: {e}")
        return None

def get_channel_videos(channel_id: str, api_key: Optional[str] = None) -> List[Dict]:
    """Fetch all videos from a YouTube Channel"""
    api_key = api_key or os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        raise ValueError("YouTube API key is required")
    
    youtube = build('youtube', 'v3', developerKey=api_key)
    videos = []
    next_page_token = None

    try:
        while True:
            # First get playlist ID for channel's uploads
            channel_response = youtube.channels().list(
                part='contentDetails',
                id = channel_id
            ).execute()

            playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

            # Get playlist items (videos)
            playlist_response = youtube.playlistItems().list(
                part='snippet',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            # Get video IDs from playlist items
            video_ids = [item['snippet']['resourceId']['videoId']
                         for item in playlist_response['items']]
            
            # Get detailed video information
            video_response = youtube.videos().list(
                part='snippet,contentDetails,statistics',
                id=",".join(video_ids)
            ).execute()

            for video in video_response['items']:
                video_info = process_video_data(video)
                videos.append(video_info)

            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token:
                break

        return videos
    
    except HttpError as e:
        print(f"Error fetching videos: {e}")
        return []

def process_video_data(video: Dict) -> Dict:
    """Process raw video into formatted statistics"""
    published_at = datetime.strptime(
        video['snippet']['publishedAt'],
        '%Y-%m-%dT%H:%M:%SZ'
    ).replace(tzinfo=timezone.utc)

    current_time = datetime.now(timezone.utc)
    days_since_publish = (current_time - published_at).days
    days_since_publish = max(days_since_publish, 1) # Avoid division by zero

    # Get engagement metrics
    stats = video['statistics']
    views = int(stats.get('viewCount', 0))
    likes = int(stats.get('likeCount', 0))
    favorites = int(stats.get('favoriteCount', 0))
    comments = int(stats.get('commentCount', 0))

    return {
        # Video Information
        'title': video['snippet']['title'],
        'published_at': published_at.strftime('%B %d, %Y'),
        'duration': video['contentDetails']['duration'],
        'description': video['snippet']['description'],
        'tags': video['snippet'].get('tags', []),
        
        # Engagement Metrics
        'views': views,
        'likes': likes,
        'favorites': favorites,
        'comment_count': comments,
        
        # Daily Rates
        'views_per_day': round(views / days_since_publish, 2),
        'likes_per_day': round(likes / days_since_publish, 2),
        'comments_per_day': round(comments / days_since_publish, 2),
        'favorites_per_day': round(favorites / days_since_publish, 2)
    }

def format_video_stats(channel_stats: Dict, videos_info: List[Dict]) -> str:
    """Format track statistics into a readable string"""
    if not channel_stats or not videos_info:
        return "No channel or video information available"
                
    output = f"""
Channel Information:
Name: {channel_stats['channel_name']}
Subscribers: {channel_stats['subscriber_count']:,}
Total Videos: {channel_stats['video_count']:,}
Total Views: {channel_stats['view_count']:,}
Created: {channel_stats['created_at']}
Description: {channel_stats['description']}

Found {len(videos_info)} videos:"""

    for video in videos_info:
        output += f"""

Video Information:
Title: {video['title']}
Published: {video['published_at']}
Duration: {video['duration']}
Description: {video['description'][:500]}... # Truncated for readability
Tags: {', '.join(video['tags'][:10])}... # First 5 tags

Engagement Metrics:
Views: {video['views']:,}
Likes: {video['likes']:,}
Favorites: {video['favorites']:,}
Comments: {video['comment_count']:,}

Daily Rates:
Views per day: {video['views_per_day']:,.2f}
Likes per day: {video['likes_per_day']:,.2f}
Comments per day: {video['comments_per_day']:,.2f}
Favorites per day: {video['favorites_per_day']:,.2f}
{'-' * 50}"""
    
    return output

if __name__ == "__main__":
    # Example usage
    channel_id = "UCVl2Q900bc0jqh27Ffx9VPA"  # Google Developers channel
    api_key = os.getenv('YOUTUBE_API_KEY')
    
    if not api_key:
        print("Error: No YouTube API key found in environment variables")
        print("Please set YOUTUBE_API_KEY in your .env file")
        exit(1)
        
    print(f"Using API key: {api_key[:5]}...")
    print(f"Fetching stats for channel ID: {channel_id}")
    
    try:
        channel_stats = get_youtube_channel_stats(channel_id, api_key)
        if not channel_stats:
            print("Error: Could not fetch channel stats")
            exit(1)
            
        print("\nChannel stats retrieved successfully!")
        print(f"Channel name: {channel_stats['channel_name']}")
        
        print("\nFetching video information...")
        videos_info = get_channel_videos(channel_id, api_key)
        if not videos_info:
            print("Error: Could not fetch video information")
            exit(1)
            
        print(f"Retrieved information for {len(videos_info)} videos")
        
        print("\nFormatting statistics...")
        formatted_stats = format_video_stats(channel_stats, videos_info)
        print("\n" + formatted_stats)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        print(traceback.format_exc())