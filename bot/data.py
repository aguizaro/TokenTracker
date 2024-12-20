import sys
from datetime import datetime

import requests
from models import Pair

# -------------------- API Functions ------------------------------------------


async def is_valid_coin(address: str) -> bool:
    """
    Check if a coin is valid

        Parameters:
            address (str): The address to check

        Returns:
            bool: True if the coin is valid, False otherwise
    """
    response = requests.get(
        f"https://api.dexscreener.com/latest/dex/tokens/{address}",
        headers={},
    )
    if response.status_code != 200:
        # log error
        return False

    data = response.json()
    return data.get("pairs") is not None


# -------------------- Helper Functions ---------------------------------------


async def get_market_cap(address: str) -> float:
    """
    Get the market cap of a pair

        Parameters:
            pair (Pair): The pair to get the market cap for

        Returns:
            float: The market cap of the pair
    """
    pairs = await search_pairs(address)
    if not pairs or len(pairs) > 1:
        print(f"Error: Invalid pair - too many pairs returned: {len(pairs)}")
        return None
    pair = pairs[0]
    return pair.marketCap if pair.marketCap else 0.0


async def list_pairs(pairs: list[Pair]) -> list[str]:
    """
    List the pairs for user selection
        Parameters:
            pairs (list): The list of pairs to display

        Returns:
            tuple: the markdown string representation of the pairs
    """
    max_pairs = 4
    selections = []
    for i, pair in enumerate(pairs):
        if i >= max_pairs - 1:
            break
        selections.append(
            f"# {i+1}. {pair.baseToken.symbol}/{pair.quoteToken.symbol}\n{display_pair(pair)}"
        )
    return selections


async def search_pairs(query: str) -> list:
    """
    Search for pairs matching the query

        Parameters:
            query (str): The query to search for in the token pairs
        Returns:
           array: An array of token pairs matching the query
    """
    response = requests.get(
        f"https://api.dexscreener.com/latest/dex/search?q={query}",
        headers={},
    )
    if response.status_code != 200:
        # log error
        return None

    data = response.json()
    if data.get("pairs") is None:
        # log error
        return None

    pairs = []
    for pair in data.get("pairs"):
        pairs.append(Pair(**pair))

    return pairs


def display_pair(pair: Pair) -> str:
    """
    Provides a markdown output of the pair
            Parameters:
                pair (Pair): The pair to display

            Returns:
                str: A markdown string of the pair
    """

    chainId = pair.chainId if pair.chainId else "na"
    dexId = pair.dexId if pair.dexId else "na"
    url = pair.url if pair.url else "na"
    pairAddress = pair.pairAddress if pair.pairAddress else "na"

    baseTokenName = pair.baseToken.name if pair.baseToken.name else "na"
    baseTokenSymbol = pair.baseToken.symbol if pair.baseToken.symbol else "na"
    baseTokenAddress = pair.baseToken.address if pair.baseToken.address else "na"

    quoteTokenName = pair.quoteToken.name if pair.quoteToken.name else "na"
    quoteTokenSymbol = pair.quoteToken.symbol if pair.quoteToken.symbol else "na"
    quoteTokenAddress = pair.quoteToken.address if pair.quoteToken.address else "na"

    priceNative = pair.priceNative if pair.priceNative else "na"
    priceUsd = pair.priceUsd if pair.priceUsd else "na"

    if pair.volume:
        h24_volume = pair.volume.h24 if pair.volume.h24 else "na"
        h6_volume = pair.volume.h6 if pair.volume.h6 else "na"
        h1_volume = pair.volume.h1 if pair.volume.h1 else "na"
        m5_volume = pair.volume.m5 if pair.volume.m5 else "na"
    else:
        h24_volume = "na"
        h6_volume = "na"
        h1_volume = "na"
        m5_volume = "na"

    m5_price_change = pair.priceChange.m5 if pair.priceChange.m5 else "na"
    h1_price_change = pair.priceChange.h1 if pair.priceChange.h1 else "na"
    h6_price_change = pair.priceChange.h6 if pair.priceChange.h6 else "na"
    h24_price_change = pair.priceChange.h24 if pair.priceChange.h24 else "na"

    if pair.liquidity:
        liquidity_usd = pair.liquidity.usd if pair.liquidity.usd else "na"
        liquidity_base = pair.liquidity.base if pair.liquidity.base else "na"
        liquidity_quote = pair.liquidity.quote if pair.liquidity.quote else "na"
    else:
        liquidity_usd = "na"
        liquidity_base = "na"
        liquidity_quote = "na"

    fdv = pair.fdv if pair.fdv else "na"
    market_cap = pair.marketCap if pair.marketCap else "na"

    pair_created_at = (
        datetime.utcfromtimestamp(pair.pairCreatedAt / 1000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        if pair.pairCreatedAt
        else "na"
    )

    if pair.info:
        image_url = pair.info.imageUrl if pair.info.imageUrl else "na"
        header_url = pair.info.header if pair.info.header else "na"
        open_graph_url = pair.info.openGraph if pair.info.openGraph else "na"
        websites = pair.info.websites if pair.info.websites else []
        socials = pair.info.socials if pair.info.socials else []
    else:
        image_url = "na"
        header_url = "na"
        open_graph_url = "na"
        websites = []
        socials = []

    markdown = f"""
🌐 **Chain**: `{chainId}` | 🔄 **DEX**: `{dexId}` | 🔗 [URL]({url})  
📦 **Pair**: {baseTokenSymbol}/{quoteTokenSymbol} - `{pairAddress}`
🪙 **Token**: {baseTokenName} | {baseTokenSymbol} 📂 `{baseTokenAddress}`
💵 **Price (N)**: {priceNative} | 💵 **Price (USD)**: {priceUsd}  
📊 **Volume** **24h**: {h24_volume} | **6h**: {h6_volume} | **1h**: {h1_volume} | **5m**: {m5_volume}
📈 **Change** **5m**: {m5_price_change}% | **1h**: {h1_price_change}% | **6h**: {h6_price_change}% | **24h**: {h24_price_change}%
💧 **Liquidity** **USD**: ${liquidity_usd} | **Base**: {liquidity_base} | **Quote**: {liquidity_quote}  
💰 **Market Cap**: ${market_cap} | **FDV**: ${fdv}
⏳ **Created** `{pair_created_at}`  
{' '.join(f"<{site.url}>" for site in websites)} 
{' '.join(f"<{social.url}>" for social in socials)}
"""
    return markdown
