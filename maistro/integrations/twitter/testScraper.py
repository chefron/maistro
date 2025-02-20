from dotenv import load_dotenv
import os
from scraper import TwitterScraper

# Load credentials from .env
load_dotenv()
username = os.getenv('TWITTER_USERNAME')
password = os.getenv('TWITTER_PASSWORD')
email = os.getenv('TWITTER_EMAIL')

# Create scraper and try to login
scraper = TwitterScraper()
success = scraper.login(username, password, email)
print(f"Login {'succeeded' if success else 'failed'}")

if success:
    print(f"Logged in as: {scraper.username}")
    print("Cookies:", scraper.cookies)