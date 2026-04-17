import math
import logging

logger = logging.getLogger(__name__)

def compute_execution_features(snapshot: dict, target_notional_usd: float, side: str) -> dict:
    """
    Computes exact math invariants for spread, depth, slippage, and exec_score.
    """
    if not snapshot.get("success"):
        return {"error": "Snapshot failed"}
        
    try:
        ticker = snapshot.get("bookTicker", {})
        depth = snapshot.get("depth", {})
        klines = snapshot.get("klines", [])
        
        best_bid = float(ticker.get("bidPrice", 0))
        best_ask = float(ticker.get("askPrice", 0))
        
        # Sanity checks
        if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
            return {"error": "Invalid best bid/ask bounds"}
            
        mid = (best_bid + best_ask) / 2.0
        spread_bps = 10000.0 * (best_ask - best_bid) / mid
        if spread_bps < 0:
            return {"error": "Negative spread"}
            
        # Depth within 1%
        bid_depth_usd = 0.0
        ask_depth_usd = 0.0
        
        for level in depth.get("bids", []):
            price = float(level[0])
            qty = float(level[1])
            if price >= mid * 0.99:
                bid_depth_usd += price * qty
                
        for level in depth.get("asks", []):
            price = float(level[0])
            qty = float(level[1])
            if price <= mid * 1.01:
                ask_depth_usd += price * qty
                
        if bid_depth_usd + ask_depth_usd == 0:
            return {"error": "Zero depth within 1%"}
            
        imbalance = (bid_depth_usd - ask_depth_usd) / (bid_depth_usd + ask_depth_usd)
        if imbalance < -1 or imbalance > 1:
            return {"error": "Invalid depth imbalance bound"}
            
        # Slippage approximation via VWAP fill on notional q
        rem_notional = target_notional_usd
        if rem_notional <= 0:
             return {"error": "Invalid target notional"}
             
        total_qty = 0.0
        book_side = depth.get("asks", []) if side.upper() == "LONG" else depth.get("bids", [])
        
        for level in book_side:
            price = float(level[0])
            qty = float(level[1])
            level_notional = price * qty
            
            if rem_notional <= level_notional:
                fill_qty = rem_notional / price
                total_qty += fill_qty
                rem_notional = 0.0
                break
            else:
                total_qty += qty
                rem_notional -= level_notional
                
        if rem_notional > 0:
            filled_notional = target_notional_usd - rem_notional
            vwap_fill = filled_notional / total_qty if total_qty > 0 else (best_ask if side.upper() == "LONG" else best_bid)
        else:
            vwap_fill = target_notional_usd / total_qty if total_qty > 0 else mid
            
        slippage_bps = 10000.0 * abs(vwap_fill - mid) / mid
        
        # 1-minute range from klines
        latest_kline = klines[-1] if len(klines) > 0 else None
        range_bps = 0.0
        if latest_kline:
            k_high = float(latest_kline[2])
            k_low = float(latest_kline[3])
            k_close = float(latest_kline[4])
            if k_close > 0:
                range_bps = 10000.0 * (k_high - k_low) / k_close
                
        # Exec Score Mapping
        s_spread = 1.0 - min(spread_bps / 12.0, 1.0)
        s_slip = 1.0 - min(slippage_bps / 20.0, 1.0)
        s_depth = min(math.log(1.0 + min(bid_depth_usd, ask_depth_usd)) / math.log(1.0 + 50000.0), 1.0)
        
        if side.upper() == "LONG":
            s_imb = (imbalance + 1.0) / 2.0
        else:
            s_imb = 1.0 - ((imbalance + 1.0) / 2.0)  # Correct logic for shorts
            
        s_vol = 1.0 - min(range_bps / 40.0, 1.0)
        
        exec_score = 100.0 * (0.25*s_spread + 0.25*s_slip + 0.20*s_depth + 0.20*s_imb + 0.10*s_vol)
        if exec_score < 0 or exec_score > 100:
             return {"error": "Exec score out of bounds"}
        
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid,
            "spread_bps": spread_bps,
            "bid_depth_usd_1pct": bid_depth_usd,
            "ask_depth_usd_1pct": ask_depth_usd,
            "depth_imbalance": imbalance,
            "est_slippage_bps": slippage_bps,
            "last_1m_range_bps": range_bps,
            "exec_score": exec_score,
            "latency_ms": snapshot.get("latency_ms", 0.0)
        }
    except Exception as e:
        logger.warning(f"Error computing execution features: {e}")
        return {"error": str(e)}
