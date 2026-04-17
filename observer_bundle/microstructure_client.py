import time
import requests
import logging

logger = logging.getLogger(__name__)

BINANCE_FUTURES_URL = "https://fapi.binance.com"

class MicrostructureClient:
    """Synchronous fetcher for Binance USD(S)-M microstructure at signal emission."""
    
    def __init__(self, base_url=BINANCE_FUTURES_URL):
        self.base_url = base_url
        self.session = requests.Session()
        
    def fetch_snapshot(self, symbol: str) -> dict:
        """
        Fetches best bid/ask, L2 depth (100 levels), and 1m klines (latency measured).
        Total explicit Binance API weigh: 8.
        Do NOT add aggTrades without considering rate limit impact.
        """
        start_t = time.time()
        
        try:
            # 1. Book Ticker (Weight 2)
            ticker_res = self.session.get(
                f"{self.base_url}/fapi/v1/ticker/bookTicker", 
                params={"symbol": symbol}, 
                timeout=2.0
            )
            ticker_res.raise_for_status()
            ticker_data = ticker_res.json()
            
            # 2. Depth 100 (Weight 5)
            depth_res = self.session.get(
                f"{self.base_url}/fapi/v1/depth", 
                params={"symbol": symbol, "limit": 100}, 
                timeout=2.0
            )
            depth_res.raise_for_status()
            depth_data = depth_res.json()
            
            # 3. Klines 1m (Weight 1)
            klines_res = self.session.get(
                f"{self.base_url}/fapi/v1/klines", 
                params={"symbol": symbol, "interval": "1m", "limit": 2}, 
                timeout=2.0
            )
            klines_res.raise_for_status()
            klines_data = klines_res.json()
            
            latency_ms = (time.time() - start_t) * 1000.0
            
            return {
                "symbol": symbol,
                "bookTicker": ticker_data,
                "depth": depth_data,
                "klines": klines_data,
                "latency_ms": latency_ms,
                "success": True
            }
            
        except Exception as e:
            latency_ms = (time.time() - start_t) * 1000.0
            logger.warning(f"MicrostructureClient fetch failed for {symbol}: {e}")
            return {
                "symbol": symbol,
                "success": False,
                "latency_ms": latency_ms,
                "error": str(e)
            }
