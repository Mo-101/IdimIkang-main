import httpx
import pandas as pd
from datetime import datetime, timezone

async def fetch_klines(pair: str, interval: str, limit: int = 1000, end_time: int = None):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": pair, "interval": interval, "limit": limit}
    if end_time:
        params["endTime"] = end_time

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
    ])

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    # CRITICAL: No signal from open candles (FINALIZED DATA ONLY)
    current_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    df = df[df["close_time"] < current_time_ms].copy()

    return df

async def fetch_historical_klines(pair: str, interval: str, total_candles: int = 8640):
    """
    Pagination (MANDATORY). Binance max = 1000 candles.
    Must fetch full ~8640 candles (90 days) if requested.
    """
    all_data = []
    end_time = None
    remaining = total_candles

    while remaining > 0:
        limit = min(1000, remaining)
        df = await fetch_klines(pair, interval, limit=limit, end_time=end_time)
        if df.empty:
            break
        all_data.append(df)
        
        # Set end_time to the open_time of the earliest candle minus 1ms
        end_time = int(df.iloc[0]["open_time"]) - 1
        remaining -= len(df)

    if not all_data:
        return pd.DataFrame()

    final_df = pd.concat(all_data).drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
    return final_df.tail(total_candles)
