from datetime import datetime, timezone
import requests
import os
from dotenv import load_dotenv

load_dotenv()

def get_user_tracks_data(user_id: str, client_id: str):
    """Fetch data for a user's tracks from Soundcloud API"""
    user_id = user_id or os.getenv('SOUNCLOUD_USER_ID')
    client_id = client_id or os.getenv('SOUNDCLOUD_CLIENT_ID')
    
    if not user_id or not client_id:
        raise ValueError("Missing required SoundCloud credentials")

    base_url = f'https://api-v2.soundcloud.com/users/{user_id}/tracks'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json'
    }
    
    all_tracks_info = []
    next_href = f"{base_url}?client_id={client_id}"
    
    try:
        while next_href:
            response = requests.get(next_href, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Process each track in the collection
            for track in data['collection']:
                created_at = datetime.strptime(
                    track['created_at'], 
                    '%Y-%m-%dT%H:%M:%SZ'
                    ).replace(tzinfo=timezone.utc)
                
                formatted_date = created_at.strftime('%B %d, %Y')

                current_time = datetime.now(timezone.utc)
                days = (current_time - created_at).days
                days_since_creation = days if days > 0 else 1

                track_info = {
                    'title': track['title'],
                    'artist': track['user']['username'],
                    'genre': track['genre'],
                    'created_at': formatted_date,
                    'duration_ms': track['duration'],
                    'duration_minutes': round(track['duration'] / 60000, 2),
                    'description': track['description'],
                    'tags': track['tag_list'],
                    'likes_count': track['likes_count'],
                    'playback_count': track['playback_count'],
                    'comments_count': track['comment_count'],
                    'reposts_count': track['reposts_count'],
                    
                    'plays_per_day': round(track['playback_count'] / days_since_creation, 2),
                    'likes_per_day': round(track['likes_count'] / days_since_creation, 2),
                    'comments_per_day': round(track['comment_count'] / days_since_creation, 2),
                    'reposts_per_day': round(track['reposts_count'] / days_since_creation, 2)
                }
                all_tracks_info.append(track_info)
            
            # Get the next page URL if it exists
            next_href = data.get('next_href')
            if next_href and 'client_id' not in next_href:
                next_href = f"{next_href}&client_id={client_id}"
            
        return all_tracks_info
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching tracks: {e}")
        return None

def format_track_stats(tracks_info) -> str:
    "Format track statistics into a readable string"
    if not tracks_info:
        return "No track information available"
    
    output = f"\nFound {len(tracks_info)} tracks:"

    for track in tracks_info:
        output += f"""

Track Information:
Title: {track['title']}
Artist: {track['artist']}
Genre: {track['genre']}
Created: {track['created_at']}
Duration: {track['duration_minutes']} minutes
Description: {track['description']}
Tags: {track['tags']}

Engagement Metrics:
Likes: {track['likes_count']}
Plays: {track['playback_count']}
Comments: {track['comments_count']}
Reposts: {track['reposts_count']}

Daily Rates:
Plays per day: {track['plays_per_day']}
Likes per day: {track['likes_per_day']}
Comments per day: {track['comments_per_day']}
Reposts per day: {track['reposts_per_day']}
{'-' * 50}"""
    
    return output

if __name__ == "__main__":
    # Example usage with explicit IDs (alternatively can use environment variables)
    user_id = '1471371707'
    client_id = 'F3QWu4vVHIWXxyHXFTxhItd9dKFwKCUa'
    
    tracks_info = get_user_tracks_data(user_id, client_id)
    if tracks_info:
        formatted_stats = format_track_stats(tracks_info)
        print(formatted_stats)