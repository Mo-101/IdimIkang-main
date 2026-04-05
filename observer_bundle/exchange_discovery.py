#!/usr/bin/env python3
"""
exchange_discovery.py
Handles dynamic universe discovery for Binance Futures top-30 by liquidity.
"""

import requests
import logging
from typing import List

# Setup simple logging for the module
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

BINANCE_FUTURES_URL = "https://fapi.binance.com"

def get_top_liquid_symbols(limit: int = 30) -> List[str]:
    """
    Returns the top N symbols by 24h quoteVolume from Binance Futures.
    Filters for USDT perpetual contracts that are currently TRADING.
    """
    try:
        # Step 1: Get exchange info for symbol metadata
        info_resp = requests.get(f"{BINANCE_FUTURES_URL}/fapi/v1/exchangeInfo", timeout=15)
        info_resp.raise_for_status()
        info_data = info_resp.json()

        symbols_meta = {}
        for s in info_data['symbols']:
            # Only USDT perpetuals that are TRADING
            if s['quoteAsset'] == 'USDT' and s['contractType'] == 'PERPETUAL' and s['status'] == 'TRADING':
                symbols_meta[s['symbol']] = True

        # Step 2: Get 24h tickers to rank by liquidity
        ticker_resp = requests.get(f"{BINANCE_FUTURES_URL}/fapi/v1/ticker/24hr", timeout=15)
        ticker_resp.raise_for_status()
        tickers = ticker_resp.json()

        # Rank by quoteVolume (total value traded in USDT)
        ranked_symbols = []
        for t in tickers:
            symbol = t['symbol']
            if symbol in symbols_meta:
                # Store symbol and its 24h quote volume
                ranked_symbols.append({
                    'symbol': symbol,
                    'quoteVolume': float(t['quoteVolume'])
                })

        # Sort by quoteVolume descending
        ranked_symbols.sort(key=lambda x: x['quoteVolume'], reverse=True)

        # Extract top N
        top_n = [x['symbol'] for x in ranked_symbols[:limit]]
        
        logging.info(f"Discovered top {len(top_n)} symbols by liquidity.")
        return top_n

    except Exception as e:
        logging.error(f"Error discovering futures universe: {e}")
        # Baseline fallback if discovery fails
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

if __name__ == "__main__":
    # Test execution
    print(get_top_liquid_symbols(30))
