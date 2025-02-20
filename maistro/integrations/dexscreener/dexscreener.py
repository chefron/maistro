from datetime import datetime
import requests
from typing import Dict, List, Optional
import logging

logger = logging.getLogger('maistro.integrations.platforms.dexscreener')

def get_token_data(chain_id: str, token_address: str) -> Optional[Dict]:
    """Fetch token trading data from DexScreener
    
    Args:
        chain_id: the chain the token is issued on (e.g. 'solana', 'ethereum', 'bsc')
        token_address: the token's contract address

    Returns:
        Dictionary containing token data or None if request fails
    """
    url = f"https://api.dexscreener.com/tokens/v1/{chain_id}/{token_address}"

    try:
        response = requests.get(url, headers={}, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or not isinstance(data, list) or not data:
            logger.warning(f"No trading pairs found for token {token_address} on {chain_id}")
            return None
        
        # Use the first pair
        return data[0]
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching token data: {e}")
        return None
    except ValueError as e:
        logger.error(f"Error parsing response: {e}")
        return None

def format_token_stats(data: Dict) -> str:
    """Format token data into a readable string"""
    if not data:
        return "No token trading data available"
    
    base_token = data['baseToken']
    quote_token=data['quoteToken']

    output = f"""
Token Information:
Name: {base_token['name']}
Symbol: {base_token['symbol']}
Chain: {data['chainId']}
Contract Address ("CA"): {base_token['address']}

Market Metrics:
Current Price: ${float(data.get('priceUsd', 0)):.8f}
24h Price Change: {data.get('priceChange', {}).get('h24', 0):+.2f}%
Market Cap: ${float(data.get('marketCap', 0)):,.2f}
24h Volume: ${float(data.get('volume', {}).get('h24', 0)):,.2f}

Trading Activity (24h):
Buy Transactions: {data.get('txns', {}).get('h24', {}).get('buys', 0):,}
Sell Transactions: {data.get('txns', {}).get('h24', {}).get('sells', 0):,}"""

    return output

if __name__ == "__main__":
    chain_id = "solana"
    token_address = "Ex5F1bfGE4nnbMut7VTBFx8eFq4Z9mkhKvCsTdeHpump"  # $llamagang

    try:
        token_data = get_token_data(chain_id, token_address)
        if token_data:
            formatted_stats = format_token_stats(token_data)
            print(formatted_stats)
        else:
            print("Could not fetch token data")
        
    except Exception as e:
        print(f"Error: {str(e)}")