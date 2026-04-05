#!/usr/bin/env python3
"""
ls_ratio_collector.py
Polls Binance Futures top long/short account ratio (15m period) every 15 minutes.
Stores to ls_ratios table.
"""

import os
import time
import logging
import requests
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Log directory check
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/ls_ratio_collector.log'),
        logging.StreamHandler()
    ]
)

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
BINANCE_BASE_URLS = [
    'https://fapi.binance.com',
    'https://fapi.binance.us',
    'https://api.binance.com'
]

def get_ls_ratio(symbol):
    for base_url in BINANCE_BASE_URLS:
        try:
            # Endpoint for Long/Short ratio handles as futures data
            url = f"{base_url}/futures/data/topLongShortAccountRatio?symbol={symbol}&period=15m"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    latest = data[-1]  # newest period (sorted ascending)
                    return {
                        'symbol': symbol,
                        'long_account_ratio': float(latest['longAccount']),
                        'short_account_ratio': float(latest['shortAccount']),
                        'timestamp': datetime.fromtimestamp(latest['timestamp'] / 1000.0)
                    }
            else:
                logging.warning(f"LS ratio: {base_url} returned {resp.status_code} for {symbol}")
        except Exception as e:
            logging.error(f"LS ratio error with {base_url} for {symbol}: {e}")
            continue
    return None

def create_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ls_ratios (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                long_account_ratio NUMERIC,
                short_account_ratio NUMERIC,
                timestamp TIMESTAMP NOT NULL,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timestamp)
            );
            CREATE INDEX IF NOT EXISTS idx_ls_symbol_time ON ls_ratios (symbol, timestamp);
        """)
        conn.commit()
        logging.info("Table ls_ratios verified/created")

def store_ls_ratio(conn, data):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ls_ratios (symbol, long_account_ratio, short_account_ratio, timestamp)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol, timestamp) DO NOTHING
        """, (data['symbol'], data['long_account_ratio'], data['short_account_ratio'], data['timestamp']))
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

    logging.info("Starting long/short ratio collector. Polling every 15 minutes.")
    while True:
        try:
            if conn.closed:
                conn = psycopg2.connect(db_url)

            for symbol in SYMBOLS:
                ls = get_ls_ratio(symbol)
                if ls:
                    store_ls_ratio(conn, ls)
                    logging.info(f"Stored {symbol} LS ratios: L={ls['long_account_ratio']} S={ls['short_account_ratio']} at {ls['timestamp']}")
                else:
                    logging.warning(f"Could not fetch LS ratio for {symbol}")
        except Exception as e:
            logging.error(f"Error in collection loop: {e}")
            try:
                conn = psycopg2.connect(db_url)
            except:
                pass

        time.sleep(900)  # 15 minutes

if __name__ == "__main__":
    main()
