#!/usr/bin/env python3
"""
oi_collector.py
Polls Binance Futures open interest every 15 minutes.
Stores to open_interest table.
"""

import os
import time
import logging
import requests
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# Log directory check
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/oi_collector.log'),
        logging.StreamHandler()
    ]
)

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
OI_ENDPOINT = 'https://fapi.binance.com/fapi/v1/openInterest'

def get_open_interest(symbol):
    try:
        resp = requests.get(OI_ENDPOINT, params={"symbol": symbol}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        oi_value = float(data['openInterest'])
        ts_ms = data.get('time')  # Binance uses "time", not "timestamp"

        if ts_ms is None:
            ts = datetime.now(timezone.utc)
        else:
            ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

        return {
            'symbol': symbol,
            'open_interest': oi_value,
            'timestamp': ts
        }
    except Exception as e:
        logging.error(f"OI error for {symbol}: {e}")
        return None

def create_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS open_interest (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                open_interest NUMERIC,
                timestamp TIMESTAMP NOT NULL,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timestamp)
            );
            CREATE INDEX IF NOT EXISTS idx_oi_symbol_time ON open_interest (symbol, timestamp);
        """)
        conn.commit()
        logging.info("Table open_interest verified/created")

def store_open_interest(conn, data):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO open_interest (symbol, open_interest, timestamp)
            VALUES (%s, %s, %s)
            ON CONFLICT (symbol, timestamp) DO NOTHING
        """, (data['symbol'], data['open_interest'], data['timestamp']))
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

    logging.info("Starting open interest collector. Polling every 15 minutes.")
    while True:
        try:
            if conn.closed:
                conn = psycopg2.connect(db_url)

            for symbol in SYMBOLS:
                oi = get_open_interest(symbol)
                if oi:
                    store_open_interest(conn, oi)
                    logging.info(f"Stored {symbol} OI {oi['open_interest']} at {oi['timestamp']}")
                else:
                    logging.warning(f"Could not fetch OI for {symbol}")
        except Exception as e:
            logging.error(f"Error in collection loop: {e}")
            try:
                conn = psycopg2.connect(db_url)
            except:
                pass

        time.sleep(900)  # 15 minutes

if __name__ == "__main__":
    main()
