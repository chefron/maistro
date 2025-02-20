from datetime import datetime
import os
from typing import Dict, List, Optional
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

load_dotenv()

def get_spotify_artist_stats(
    artist_id: str, 
    client_id: Optional[str] = None, 
    client_secret: Optional[str] = None
) -> Optional[Dict]:
    """Fetch basic statistics for a Spotify artist"""
    client_id = client_id or os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = client_secret or os.getenv('SPOTIFY_CLIENT_SECRET')

    if not client_id or not client_secret:
        raise ValueError("Spotify client credentials are required")
    
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)

        # Get artist info
        artist = sp.artist(artist_id)

        # Get artist's top tracks
        top_tracks = sp.artist_top_tracks(artist_id)

        return {
            'artist_name': artist['name'],
            'genres': artist['genres'],
            'follower_count': artist['followers']['total'],
            'popularity': artist['popularity'],
            'top_tracks': [
                {
                    'name': track['name'],
                    'popularity': track['popularity'],
                    'duration_ms': track['duration_ms'],
                    'duration_minutes': round(track['duration_ms'] / 60000, 2),
                    'album': track['album']['name'],
                    'release_date': track['album']['release_date'],
                    'external_urls': track['external_urls']
                }
                for track in top_tracks['tracks']
            ]
        }
    
    except Exception as e:
        print(f"Error fetching artist stats: {e}")
        return None

def format_artist_stats(artist_stats: Dict) -> str:
    """Format artist statistics into a readable string"""
    if not artist_stats:
        return "No artist information available"
    
    output = f"""
Artist Information:
Name: {artist_stats['artist_name']}
Genres: {', '.join(artist_stats['genres'])}
Followers: {artist_stats['follower_count']:,}
Popularity Score: {artist_stats['popularity']}/100

Top Tracks:"""

    for track in artist_stats['top_tracks']:
        output += f"""

Track Information:
Title: {track['name']}
Album: {track['album']}
Released: {track['release_date']}
Duration: {track['duration_minutes']} minutes
Popularity Score: {track['popularity']}/100
Spotify URL: {track['external_urls'].get('spotify', 'N/A')}
{'-' * 50}"""
    
    return output

if __name__ == "__main__":
    # Example usage
    artist_id = "6TnQmIKskwQAUgBu7BuELr" # Dolla Llama
    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("Error: No Spotify credentials found in environment variables")
        print("Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file")
        exit(1)
        
    print(f"Using Client ID: {client_id[:5]}...")
    print(f"Fetching stats for artist ID: {artist_id}")
    
    try:
        artist_stats = get_spotify_artist_stats(artist_id, client_id, client_secret)
        if not artist_stats:
            print("Error: Could not fetch artist stats")
            exit(1)
            
        print("\nArtist stats retrieved successfully!")
        print(f"Artist name: {artist_stats['artist_name']}")
        
        print("\nFormatting statistics...")
        formatted_stats = format_artist_stats(artist_stats)
        print("\n" + formatted_stats)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        print(traceback.format_exc())