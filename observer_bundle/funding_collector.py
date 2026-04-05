#!/usr/bin/env python3
"""
funding_collector.py
Polls Binance Futures funding rate every 8 hours.
Stores to funding_rates table.
"""

import os
import time
import logging
import random
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Log directory check
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/funding_collector.log'),
        logging.StreamHandler()
    ]
)

BINANCE_BASE_URLS = [
    'https://fapi.binance.com',
    'https://fapi.binance.us',
    'https://api.binance.com'
]
DEFAULT_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XPLUSDT', 'RIVERUSDT']

def get_funding_rate(symbol):
    for base_url in BINANCE_BASE_URLS:
        try:
            url = f"{base_url}/fapi/v1/fundingRate?symbol={symbol}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    latest = data[0] if isinstance(data, list) else data
                    # Binance returns a list of history, we take the most recent
                    # If it's a list, data[0] is correct for history, but for /fundingRate?symbol= it often returns a list [ {...} ]
                    target = data[-1] if isinstance(data, list) else data
                    return {
                        'symbol': symbol,
                        'funding_rate': float(target['fundingRate']),
                        'funding_time': datetime.fromtimestamp(target['fundingTime'] / 1000.0)
                    }
            else:
                logging.warning(f"URL {base_url} returned {resp.status_code} for {symbol}")
        except Exception as e:
            logging.error(f"Error with {base_url} for {symbol}: {e}")
            continue
    return None

def create_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS funding_rates (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                funding_rate NUMERIC,
                funding_time TIMESTAMP NOT NULL,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, funding_time)
            );
            CREATE INDEX IF NOT EXISTS idx_funding_symbol_time ON funding_rates (symbol, funding_time);
        """)
        conn.commit()
        logging.info("Table funding_rates verified/created")

def store_funding_rate(conn, data):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO funding_rates (symbol, funding_rate, funding_time)
            VALUES (%s, %s, %s)
            ON CONFLICT (symbol, funding_time) DO NOTHING
        """, (data['symbol'], data['funding_rate'], data['funding_time']))
        conn.commit()

def main():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logging.error("DATABASE_URL environment variable is missing")
        return

    try:
        conn = psycopg2.connect(db_url)
        create_table(conn)
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return

    logging.info("Starting funding collector. Will run every 8 hours.")
    while True:
        try:
            # Ensure connection is alive
            if conn.closed:
                conn = psycopg2.connect(db_url)

            # Dynamic symbol discovery: everything we've traded or are watching
            symbols_to_check = set(DEFAULT_SYMBOLS)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pair FROM signals GROUP BY pair ORDER BY MAX(ts) DESC LIMIT 100")
                    db_pairs = [row[0] for row in cur.fetchall() if row[0]]
                    symbols_to_check.update(db_pairs)
            except Exception as e:
                logging.error(f"Failed to fetch dynamic symbols: {e}")

            for symbol in symbols_to_check:
                fr = get_funding_rate(symbol)
                if fr:
                    store_funding_rate(conn, fr)
                    logging.info(f"Stored {symbol} funding {fr['funding_rate']} at {fr['funding_time']}")
                else:
                    logging.info(f"Skipping {symbol} (not futures or rate limit)")
        except Exception as e:
            logging.error(f"Error in collection loop: {e}")
            try:
                conn = psycopg2.connect(db_url)
            except:
                pass
        
        # Sleep 1 hour with jitter (prevent thundering herd)
        sleep_seconds = 3600 + random.randint(-120, 120)
        logging.info(f"Cycle complete. Sleeping {sleep_seconds} seconds.")
        time.sleep(sleep_seconds)

if __name__ == "__main__":
    main()
