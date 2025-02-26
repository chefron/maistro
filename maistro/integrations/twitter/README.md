# Twitter Scraper for Maistro

This directory contains a Twitter scraper implementation for the Maistro AI agent framework.

## Recent Improvements

The Twitter scraper has been enhanced to avoid detection and blocking by Twitter's anti-bot systems. Key improvements include:

1. **TLS Cipher Randomization**: Randomizes the order of TLS ciphers to avoid fingerprinting.
2. **User Agent Rotation**: Rotates between realistic user agents to mimic different browsers and devices.
3. **Improved Cookie Handling**: Better management of cookies and session state.
4. **Realistic Headers**: Added more realistic HTTP headers that match browser requests.
5. **Random Delays**: Added randomized delays between requests to mimic human behavior.
6. **Exponential Backoff**: Improved error handling with exponential backoff for retries.
7. **More Robust Authentication Flow**: Enhanced login process with better handling of various authentication challenges.

## Usage

### Basic Usage

```python
from scraper import TwitterScraper

# Initialize the scraper
scraper = TwitterScraper()

# Login to Twitter
scraper.login(username, password, email=None, two_factor_secret=None)

# Create a tweet
scraper.create_tweet("Hello, Twitter!")
```

### Testing

Two test scripts are provided to verify the functionality of the scraper:

1. **test_scraper.py**: Tests basic guest functionality (getting a guest token and making API requests).

```bash
python maistro/integrations/twitter/test_scraper.py
```

2. **test_login.py**: Tests login functionality using credentials from the .env file.

```bash
python maistro/integrations/twitter/test_login.py [--2fa SECRET]
```

The script reads Twitter credentials from the .env file in the project root. Make sure the following environment variables are set:
- `TWITTER_USERNAME`: Your Twitter username or email
- `TWITTER_PASSWORD`: Your Twitter password
- `TWITTER_EMAIL`: Your email for verification (optional)

## Troubleshooting

If you encounter issues with the scraper:

1. **SSL Certificate Errors**: The scraper disables SSL verification for testing purposes. In a production environment, you should properly configure SSL certificates.

2. **Rate Limiting**: If you're making too many requests, Twitter may rate limit your IP address. The scraper includes exponential backoff to handle this, but you may need to wait before trying again.

3. **Login Challenges**: Twitter may require additional verification steps during login, such as email verification or two-factor authentication. Make sure to provide these parameters when calling the `login` method.

4. **Changing Endpoints**: Twitter's API endpoints may change over time. If you encounter 404 errors, check if the endpoint URLs need to be updated.

## Implementation Details

The scraper uses several techniques to avoid detection:

- **TLS Cipher Randomization**: The `TLSCipherRandomizingAdapter` class randomizes the order of TLS ciphers to avoid fingerprinting.
- **User Agent Rotation**: The scraper rotates between realistic user agents to mimic different browsers and devices.
- **Random Delays**: The scraper adds random delays between requests to mimic human behavior.
- **Exponential Backoff**: The scraper uses exponential backoff for retries when encountering errors.

These techniques are based on analysis of successful Twitter clients like the Eliza Twitter client.
