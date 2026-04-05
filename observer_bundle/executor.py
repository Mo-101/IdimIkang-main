import ccxt
import os
import logging
from dotenv import load_dotenv
from typing import Dict, Any, List

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("IdimExecutor")

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

class ExchangeHub:
    def __init__(self):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self._init_exchanges()

    def _init_exchanges(self):
        configs = {
            "binance": {
                "apiKey": os.getenv("BINANCE_API_KEY"),
                "secret": os.getenv("BINANCE_API_SECRET"),
                "options": {"defaultType": "future"}
            },
            "bybit": {
                "apiKey": os.getenv("BYBIT_API_KEY"),
                "secret": os.getenv("BYBIT_API_SECRET"),
                "options": {"defaultType": "linear"}
            },
            "okx": {
                "apiKey": os.getenv("OKX_API_KEY"),
                "secret": os.getenv("OKX_API_SECRET"),
                "password": os.getenv("OKX_API_PASSWORD"),
            },
            "bitget": {
                "apiKey": os.getenv("BITGET_API_KEY"),
                "secret": os.getenv("BITGET_API_SECRET"),
                "password": os.getenv("BITGET_API_PASSWORD"),
            }
        }

        for name, cfg in configs.items():
            if cfg["apiKey"] and cfg["secret"]:
                try:
                    exchange_class = getattr(ccxt, name)
                    self.exchanges[name] = exchange_class(cfg)
                    logger.info(f"Initialized {name.upper()} execution provider.")
                except Exception as e:
                    logger.error(f"Failed to initialize {name}: {e}")
            else:
                logger.warning(f"{name.upper()} API keys missing. Provider disabled.")

    def get_balances(self) -> Dict[str, Any]:
        balances = {}
        for name, ex in self.exchanges.items():
            try:
                bal = ex.fetch_balance()
                balances[name] = bal['total'].get('USDT', 0)
            except Exception as e:
                logger.error(f"Error fetching balance for {name}: {e}")
                balances[name] = "Error"
        return balances

    def place_order(self, exchange_name: str, symbol: str, side: str, order_type: str, amount: float, price: float = None) -> Dict[str, Any]:
        if exchange_name not in self.exchanges:
            return {"success": False, "error": f"Exchange {exchange_name} not initialized."}

        ex = self.exchanges[exchange_name]
        
        # Standardize symbol for CCXT (e.g., BTCUSDT -> BTC/USDT:USDT)
        # Note: Symbols vary by exchange in CCXT, usually handled by market loading
        try:
            ex.load_markets()
            # Simple heuristic for common futures symbols
            ccxt_symbol = symbol.replace("USDT", "/USDT:USDT") if "USDT" in symbol else symbol
            
            if DRY_RUN:
                logger.info(f"[DRY_RUN] {side} {amount} {ccxt_symbol} on {exchange_name} @ {price or 'MARKET'}")
                return {"success": True, "info": "DRY_RUN_SUCCESS", "order_id": "dry_run_123"}

            if order_type.lower() == "limit":
                order = ex.create_order(ccxt_symbol, "limit", side.lower(), amount, price)
            else:
                order = ex.create_order(ccxt_symbol, "market", side.lower(), amount)
            
            logger.info(f"Order placed on {exchange_name}: {order['id']}")
            return {"success": True, "info": order}
        except Exception as e:
            logger.error(f"Order failed on {exchange_name}: {e}")
            return {"success": False, "error": str(e)}

    def get_active_positions(self) -> List[Dict[str, Any]]:
        all_positions = []
        for name, ex in self.exchanges.items():
            try:
                positions = ex.fetch_positions()
                for p in positions:
                    if float(p.get('contracts', 0)) > 0:
                        all_positions.append({
                            "exchange": name,
                            "symbol": p.get('symbol'),
                            "side": p.get('side'),
                            "contracts": p.get('contracts'),
                            "entryPrice": p.get('entryPrice'),
                            "unrealizedPnl": p.get('unrealizedPnl')
                        })
            except Exception as e:
                logger.error(f"Error fetching positions for {name}: {e}")
        return all_positions

# Singleton manager
_hub_instance = None

def get_hub():
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = ExchangeHub()
    return _hub_instance
