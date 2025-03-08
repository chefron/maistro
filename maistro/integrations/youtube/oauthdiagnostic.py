import os
import json
import pickle
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

def force_auth_with_port():
    load_dotenv()
    
    # Get credentials from environment
    client_id = os.getenv('YOUTUBE_CLIENT_ID')
    client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("Error: Missing client credentials in environment variables")
        return None
    
    print(f"Using client ID: {client_id}")
    
    # Create client config with EXPLICIT redirect URI
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost:8080/"]
        }
    }
    
    # Create flow with fixed redirect URI
    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=['https://www.googleapis.com/auth/youtube.force-ssl']
    )
    
    # Override redirect_uri to make sure it's exactly what we want
    flow.redirect_uri = "http://localhost:8080/"
    
    print(f"Redirect URI set to: {flow.redirect_uri}")
    print("Make sure this EXACT URI is registered in your Google Cloud Console")
    
    # Generate authorization URL with explicit consent prompting
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        prompt='consent',  # Force the consent screen to appear
        include_granted_scopes='true'
    )
    
    print("Starting authentication flow with forced consent...")
    print(f"Auth URL: {auth_url}")
    
    try:
        # Force port 8080 with no room for override
        creds = flow.run_local_server(
            port=8080,
            open_browser=True,
            success_message="Authentication successful! You can close this window.",
            authorization_prompt_message="Please complete the authorization in your browser"
        )
        
        if creds and creds.refresh_token:
            print("\n✅ SUCCESS! Got refresh token.")
            print(f"Refresh token: {creds.refresh_token}")
            print("\nAdd this to your .env file as:")
            print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
            return creds
        else:
            print("\n⚠️ Authentication successful but no refresh token received.")
            print("This typically happens when there's an issue with the consent flow.")
            print("Did you definitely revoke access at https://myaccount.google.com/permissions?")
            return None
            
    except Exception as e:
        print(f"\n❌ Error during authentication: {e}")
        return None

if __name__ == "__main__":
    print("\n=== FORCE PORT 8080 OAUTH TEST ===\n")
    
    creds = force_auth_with_port()
    
    if creds:
        print("\nTesting API connection...")
        try:
            youtube = build('youtube', 'v3', credentials=creds)
            response = youtube.channels().list(part='snippet', mine=True).execute()
            
            if 'items' in response and response['items']:
                print(f"\n✅ Connected to YouTube channel: {response['items'][0]['snippet']['title']}")
            else:
                print("\n⚠️ Connected but couldn't retrieve channel details")
        except Exception as e:
            print(f"\n❌ API error: {e}")