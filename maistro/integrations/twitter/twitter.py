import tweepy
import os
import json
import sqlite3
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

class TweepyMusicAgent:
    def __init__(self, agent_name):
        # Load credentials
        self.api_key = os.getenv("TWITTER_API_KEY")
        self.api_secret = os.getenv("TWITTER_API_SECRET")
        self.access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        self.access_secret = os.getenv("TWITTER_ACCESS_SECRET")
        self.bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        
        if not all([self.api_key, self.api_secret, self.access_token, self.access_secret, self.bearer_token]):
            missing = []
            if not self.api_key: missing.append("TWITTER_API_KEY")
            if not self.api_secret: missing.append("TWITTER_API_SECRET")
            if not self.access_token: missing.append("TWITTER_ACCESS_TOKEN")
            if not self.access_secret: missing.append("TWITTER_ACCESS_SECRET")
            if not self.bearer_token: missing.append("TWITTER_BEARER_TOKEN")
            raise ValueError(f"Missing Twitter credentials: {', '.join(missing)}")
        
        # Create two clients:
        # 1) OAuth client for posting tweets...
        self.oauth_client = tweepy.Client(
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_secret
        )
        
        # ...and 2) Bearer token client for reading data
        self.read_client = tweepy.Client(
            bearer_token=self.bearer_token,
            wait_on_rate_limit=True,
            return_type=requests.Response
        )
        
        # Get and store user info
        me_response = self.oauth_client.get_me(user_fields=["username"])
        if me_response.data:
            self.user_id = me_response.data.id
            self.username = me_response.data.username
            print(f"Initialized Twitter client for @{self.username} (ID: {self.user_id})")
        else:
            raise ValueError("Could not retrieve user information")
        
        # Setup database and usage tracking
        self.agent_name = agent_name
        self.cache_db = f"{agent_name}_cache.db"
        self.usage_file = f"{agent_name}_usage.json"
        self.setup_cache()
        
        # Initialize counters and limits
        self.daily_limit = 17
        self.monthly_read_limit = 100
        self.monthly_post_limit = 500
        self.load_usage()
    
    def setup_cache(self):
        """Set up SQLite cache for tracking responses"""
        try:
            conn = sqlite3.connect(self.cache_db)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS responded_tweets (
                    tweet_id TEXT PRIMARY KEY,
                    response_time TEXT
                )
            ''')
            conn.commit()
            conn.close()
            logger.info(f"Cache database {self.cache_db} connected successfully")
        except sqlite3.Error as e:
            logger.error(f"SQLite error setting up cache: {e}")
            raise
    
    def load_usage(self):
        """Load or initialize usage tracking"""
        now = datetime.now()
        
        if not os.path.exists(self.usage_file):
            self.usage = {
                "monthly_reads": 0,
                "monthly_posts": 0,
                "daily_posts": 0,
                "last_post_date": now.strftime("%Y-%m-%d"),
                "last_reset": now.isoformat()
                }
            self.posts_used_today = 0
            self.save_usage()
        else:
            try:
                with open(self.usage_file, 'r') as f:
                    self.usage = json.load(f)

                # Check if we need to reset the daily post counter
                last_post_date = self.usage.get("last_post_date", "")
                today = now.strftime("%Y-%m-%d")

                if last_post_date != today:
                    # It's a new day so we reset the daily counter
                    self.usage["daily_posts"] = 0
                    self.usage["last_post_date"] = today
                    logger.info(f"Daily limit reset for {today}")
                
                # Set the daily post counter from the stored value
                self.posts_used_today = self.usage["daily_posts"]

                # Check monthly reset
                last_reset = datetime.fromisoformat(self.usage["last_reset"])
                if (now - last_reset) >= timedelta(days=30):
                    self.usage["monthly_reads"] = 0
                    self.usage["monthly_posts"] = 0
                    self.usage["last_reset"] = now.isoformat()
                    logger.info(f"Monthly limits reset {(now - last_reset).days} days after last reset")
                    self.save_usage()
            
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.error(f"Error loading usage file: {e}")
                self.usage = {
                    "monthly_reads": 0, 
                    "monthly_posts": 0,
                    "daily_posts": 0,
                    "last_post_date": now.strftime("%Y-%m-%d"),
                    "last_reset": now.isoformat()
                }
                self.posts_used_today = 0
                self.save_usage()
    
    def save_usage(self):
        """Save usage stats to file"""
        try:
            with open(self.usage_file, 'w') as f:
                json.dump(self.usage, f, indent=4)
                logger.debug("Usage statistics saved")
        except IOError as e:
            logger.error(f"Error saving usage statistics: {e}")
    
    def mark_responded(self, tweet_id):
        """Mark a tweet as responded to"""
        try:
            conn = sqlite3.connect(self.cache_db)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO responded_tweets (tweet_id, response_time) VALUES (?, ?)",
                (tweet_id, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
            logger.debug(f"Marked tweet {tweet_id} as responded to")
        except sqlite3.Error as e:
            logger.error(f"Error marking tweet as responded to: {e}")
    
    def has_responded(self, tweet_id):
        """Check if we've responded to a tweet"""
        try:
            conn = sqlite3.connect(self.cache_db)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM responded_tweets WHERE tweet_id = ?", (tweet_id,))
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except sqlite3.Error as e:
            logger.error(f"Error checking response status: {e}")
            return False
    
    def get_mentions(self):
        """Get recent mentions using the read client (bearer token)"""
        # Check monthly read limit first
        if self.usage["monthly_reads"] >= self.monthly_read_limit:
            logger.warning(f"⚠️ Monthly read limit reached: {self.usage['monthly_reads']}/{self.monthly_read_limit}")
            return []
            
        try:
            # Use the read_client with bearer token for this
            response = self.read_client.get_users_mentions(
                self.user_id,
                expansions=["author_id"],
                user_fields=["username"],
                max_results=10
            )
            
            # Print full response information
            print("=== RESPONSE INFO ===")
            print(f"Status Code: {response.status_code}")
            print("=== HEADERS ===")
            for key, value in response.headers.items():
                print(f"{key}: {value}")
            
            # Print rate limit headers specifically
            print("\n=== RATE LIMITS ===")
            limit = response.headers.get('x-rate-limit-limit')
            remaining = response.headers.get('x-rate-limit-remaining')
            reset_time = response.headers.get('x-rate-limit-reset')
            print(f"Limit: {limit}, Remaining: {remaining}, Reset: {reset_time}")
            
            if reset_time:
                reset_datetime = datetime.fromtimestamp(int(reset_time))
                print(f"Reset Time: {reset_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Now we need to parse the JSON response manually
            response_json = response.json()
            
            # Increment read counter
            self.usage["monthly_reads"] += 1
            self.save_usage()
            logger.info(f"🔍 Monthly reads: {self.usage['monthly_reads']}/{self.monthly_read_limit}")
            
            # Check if we have data
            if 'data' not in response_json or not response_json['data']:
                logger.info("No mentions found")
                return []
            
            # Process mentions and exclude self-mentions
            results = []
            users = {user['id']: user['username'] 
                    for user in response_json.get('includes', {}).get('users', [])} if 'includes' in response_json else {}
            
            for mention in response_json['data']:
                # Skip if it's from me or if we've already responded
                if mention['author_id'] == self.user_id or self.has_responded(mention['id']):
                    continue
                    
                results.append({
                    "id": mention['id'],
                    "text": mention['text'],
                    "author_id": mention['author_id'],
                    "username": users.get(mention['author_id'], "unknown")
                })
            
            return results
                
        except tweepy.TweepyException as e:
            logger.error(f"Error fetching mentions: {e}")
            return []
    
    def post_tweet(self, text):
        """Post a tweet using Tweepy"""
        # Check daily limit first
        if self.posts_used_today >= self.daily_limit:
            logger.warning(f"Daily limit reached: {self.posts_used_today}/{self.daily_limit}")
            return False
            
        # Check monthly limit too
        if self.usage["monthly_posts"] >= self.monthly_post_limit:
            logger.warning(f"Monthly post limit reached: {self.usage['monthly_posts']}/{self.monthly_post_limit}")
            return False
            
        try:
            response = self.oauth_client.create_tweet(text=text)
            self.posts_used_today += 1
            self.usage["daily_posts"] = self.posts_used_today  # Update stored value of daily post counter
            self.usage["monthly_posts"] += 1
            self.save_usage()
            logger.info(f"Tweet posted! Daily posts used: {self.posts_used_today}/{self.daily_limit}")
            logger.info(f"Monthly posts: {self.usage['monthly_posts']}/{self.monthly_post_limit}")
            return True
            
        except tweepy.TweepyException as e:
            if "429" in str(e):
                logger.error("Posting rate limit reached.")
            else:
                logger.error(f"Error posting tweet: {e}")
            return False
    
    def reply_to_tweet(self, tweet_id, text):
        """Reply to a specific tweet"""
        # Check if we've already responded to this tweet
        if self.has_responded(tweet_id):
            logger.info(f"Already responded to tweet {tweet_id}")
            return False
            
        # Check daily limit
        if self.posts_used_today >= self.daily_limit:
            logger.warning(f"Daily limit reached: {self.posts_used_today}/{self.daily_limit}")
            return False
            
        # Check monthly limit
        if self.usage["monthly_posts"] >= self.monthly_post_limit:
            logger.warning(f"Monthly post limit reached: {self.usage['monthly_posts']}/{self.monthly_post_limit}")
            return False
            
        try:
            response = self.oauth_client.create_tweet(
                text=text,
                in_reply_to_tweet_id=tweet_id
            )
            
            # Mark as responded and update counters
            self.mark_responded(tweet_id)
            self.posts_used_today += 1
            self.usage["daily_posts"] = self.posts_used_today  # Update stored value of daily post counter
            self.usage["monthly_posts"] += 1
            self.save_usage()
            
            logger.info(f"Reply posted! Daily posts used: {self.posts_used_today}/{self.daily_limit}")
            logger.info(f"Monthly posts: {self.usage['monthly_posts']}/{self.monthly_post_limit}")
            return True
            
        except tweepy.TweepyException as e:
            if "429" in str(e):
                logger.error("Replying rate limit reached.")
            else:
                logger.error(f"Error posting reply: {e}")
            return False
    
    def respond_to_all_mentions(self):
        """Get and respond to all unhandled mentions"""
        mentions = self.get_mentions()
        logger.info(f"Found {len(mentions)} new mentions to process")
        
        response_count = 0
        for mention in mentions:
            # Skip if we're out of daily posts
            if self.posts_used_today >= self.daily_limit:
                logger.warning("Daily post limit reached, stopping responses")
                break
                
            # Generate reply (you could use an LLM here)
            reply_text = f"@{mention['username']} Thanks for the mention!"
            
            # Post the reply
            if self.reply_to_tweet(mention['id'], reply_text):
                logger.info(f"Replied to @{mention['username']}")
                response_count += 1
            else:
                logger.error(f"Failed to reply to @{mention['username']}")
                
        return response_count

# Example usage
if __name__ == "__main__":
    # Create agent
    agent = TweepyMusicAgent("dolla-llama")
    
    # Post a test tweet
    agent.post_tweet("7th test")
    
    # Check and respond to mentions
    agent.respond_to_all_mentions()