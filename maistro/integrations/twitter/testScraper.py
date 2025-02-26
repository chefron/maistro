from dotenv import load_dotenv
import os
from scraper import TwitterScraper

# Load credentials from .env
print("\nLoading credentials from .env file...")
load_dotenv()
username = os.getenv('TWITTER_USERNAME')
password = os.getenv('TWITTER_PASSWORD')
email = os.getenv('TWITTER_EMAIL')

# Debug credential loading
print(f"\nCredentials loaded from .env:")
print(f"Username present: {'Yes' if username else 'No'}")
print(f"Password present: {'Yes' if password else 'No'}")
print(f"Email present: {'Yes' if email else 'No'}")

if not all([username, password]):
    print("Error: Missing required credentials in .env file")
    exit(1)

# Create scraper and try to login
print("\nCreating TwitterScraper instance...")
scraper = TwitterScraper()

print("\nAttempting to login...")
success = scraper.login(username, password, email)
print(f"\nLogin {'succeeded' if success else 'failed'}")

if success:
    print(f"Logged in as: {scraper.username}")
    
    # Try to create a test tweet
    try:
        tweet_text = "Testing my automated Twitter posting system! 🤖 #Python #Automation"
        print(f"\nAttempting to create tweet: {tweet_text}")
        result = scraper.create_tweet(tweet_text)
        print("\nTweet created successfully!")
        print("Response:", result)
    except Exception as e:
        print(f"\nFailed to create tweet: {e}")
else:
    print("\nLogin failed - cannot proceed with tweet creation")