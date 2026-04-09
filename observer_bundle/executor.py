import ccxt
import os
import logging
import random
import time
from dotenv import load_dotenv
from typing import Dict, Any, List

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("IdimExecutor")

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

class SimulationExchange:
    """A mock exchange for tactical UI simulation when API keys are missing."""
    def __init__(self, name: str):
        self.name = name
        self.is_simulated = True
        self.precision = 2
        self.sim_balance = 10000.0
        self.sim_positions = []

    def load_markets(self): pass

    def fetch_balance(self):
        return {'total': {'USDT': self.sim_balance}, 'free': {'USDT': self.sim_balance}}

    def fetch_ticker(self, symbol: str):
        # Generate stable-ish random price movement around a baseline
        # Using a fixed seed based on symbol to keep it consistent-ish
        random.seed(symbol + str(int(time.time() / 10))) 
        base = 65000 if "BTC" in symbol else (2500 if "ETH" in symbol else 100)
        last = base + random.uniform(-10, 10)
        return {
            'last': last,
            'percentage': random.uniform(-5, 5),
            'bid': last - 0.1,
            'ask': last + 0.1,
            'high': last + 5,
            'low': last - 5,
            'quoteVolume': random.uniform(100000, 1000000)
        }

    def set_margin_mode(self, mode, symbol): 
        logger.info(f"[SIM] {self.name} Mode set to {mode}")

    def set_leverage(self, leverage, symbol):
        logger.info(f"[SIM] {self.name} Leverage set to {leverage}")

    def create_order(self, symbol, type, side, amount, price=None, params={}):
        logger.info(f"[SIM] {self.name} Order: {side} {amount} {symbol}")
        return {'id': f'sim_order_{random.randint(1000, 9999)}', 'info': 'SIMULATED_SUCCESS'}

    def fetch_positions(self, symbols=None):
        return []

class ExchangeHub:
    def __init__(self):
        self.exchanges: Dict[str, Any] = {}
        self._init_exchanges()

    def _init_exchanges(self):
        # Mandated Staged Rollout (v1.9.4): Selective Keying
        # Provisioned: Binance, Bybit, OKX
        # Deferred: Bitget, Gate, HTX, KuCoin, SuperEx
        
        configs = {
            "binance": {
                "apiKey": os.getenv("BINANCE_API_KEY"),
                "secret": os.getenv("BINANCE_API_SECRET"),
                "options": {"defaultType": "future", "adjustForTimeDifference": True}
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
            }
        }

        # Full 8-vault roster for the UI
        roster = ["binance", "bybit", "okx", "bitget", "gate", "htx", "kucoinfutures", "superex"]

        for name in roster:
            cfg = configs.get(name)
            if cfg and cfg.get("apiKey") and cfg.get("secret"):
                try:
                    ccxt_name = name
                    exchange_class = getattr(ccxt, ccxt_name)
                    ex = exchange_class(cfg)
                    
                    # Test connection / balance fetch as proof-of-auth
                    bal = ex.fetch_balance()
                    ex.is_simulated = False
                    self.exchanges[name] = ex
                    logger.info(f"Initialized {name.upper()} execution provider (LIVE). Balance: {bal.get('total', {}).get('USDT', 0)}")
                except Exception as e:
                    logger.error(f"Failed to initialize live {name}: {e}")
                    self.exchanges[name] = SimulationExchange(name)
            else:
                self.exchanges[name] = SimulationExchange(name)
                # Only log as 'SIM' if it was a target for provisioning
                if name in configs:
                    logger.warning(f"{name.upper()} provisioned but keys missing. Falling back to SIM.")
                else:
                    logger.info(f"Initialized {name.upper()} simulation provider (STAGED/DEFERRED).")

    def get_balances(self) -> Dict[str, Any]:
        balances = {}
        for name, ex in self.exchanges.items():
            try:
                # CCXT fetch_balance wrapper
                bal = ex.fetch_balance()
                # For futures, 'USDT' is usually in 'total'
                balances[name] = bal['total'].get('USDT', 0)
            except Exception as e:
                logger.error(f"Error fetching balance for {name}: {e}")
                balances[name] = "Error"
        return balances

    def set_margin_mode(self, exchange_name: str, symbol: str, mode: str) -> Dict[str, Any]:
        if exchange_name not in self.exchanges:
            return {"success": False, "error": f"Exchange {exchange_name} not found."}
        
        ex = self.exchanges[exchange_name]
        try:
            ex.load_markets()
            ccxt_symbol = symbol.replace("USDT", "/USDT:USDT") if "USDT" in symbol else symbol
            
            # Diagnostic for dispatch rule v1.9.4
            if not getattr(ex, 'is_simulated', False):
                logger.info(f"[STAGED_ROLLOUT] Syncing margin mode for {exchange_name} {ccxt_symbol} -> {mode.upper()}")

            ex.set_margin_mode(mode.lower(), ccxt_symbol)
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to set margin mode on {exchange_name}: {e}")
            return {"success": False, "error": str(e)}

    def set_leverage(self, exchange_name: str, symbol: str, leverage: int) -> Dict[str, Any]:
        if exchange_name not in self.exchanges:
            return {"success": False, "error": "Exchange not found"}
        
        ex = self.exchanges[exchange_name]
        try:
            ex.load_markets()
            ccxt_symbol = symbol.replace("USDT", "/USDT:USDT") if "USDT" in symbol else symbol
            
            if not getattr(ex, 'is_simulated', False):
                logger.info(f"[STAGED_ROLLOUT] Syncing leverage for {exchange_name} {ccxt_symbol} -> {leverage}x")

            ex.set_leverage(leverage, ccxt_symbol)
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to set leverage on {exchange_name}: {e}")
            return {"success": False, "error": str(e)}

    def get_ticker_data(self, exchange_name: str, symbol: str) -> Dict[str, Any]:
        if exchange_name not in self.exchanges:
             return {"error": "Exchange not found"}
        
        ex = self.exchanges[exchange_name]
        try:
            ccxt_symbol = symbol.replace("USDT", "/USDT:USDT") if "USDT" in symbol else symbol
            ticker = ex.fetch_ticker(ccxt_symbol)
            return {
                "last": ticker['last'],
                "percentage": ticker['percentage'],
                "bid": ticker['bid'],
                "ask": ticker['ask'],
                "high": ticker['high'],
                "low": ticker['low'],
                "volume": ticker['quoteVolume']
            }
        except Exception as e:
            # Silent fallback to Simulation if live ticker fails
            return SimulationExchange(exchange_name).fetch_ticker(symbol)

    def place_order(self, exchange_name: str, symbol: str, side: str, order_type: str, amount: float, price: float = None, params: dict = {}) -> Dict[str, Any]:
        """
        Mandated Execution Logic (v1.9.4):
        DISPATCH = SIM ONLY unless ENABLE_LIVE_TRADING is true.
        """
        if exchange_name not in self.exchanges:
            return {"success": False, "error": f"Exchange {exchange_name} not initialized."}

        ex = self.exchanges[exchange_name]
        ccxt_symbol = symbol.replace("USDT", "/USDT:USDT") if "USDT" in symbol else symbol
        
        is_simulated = getattr(ex, 'is_simulated', False)
        
        # Check if live trading is globally enabled and exchange is not in simulation mode
        if config.ENABLE_LIVE_TRADING and not is_simulated:
            try:
                logger.info(f"[LIVE_DISPATCH] {exchange_name} | {side} {amount} {ccxt_symbol} | Type: {order_type}")
                
                # Strip SL/TP from params to avoid passing them directly if not supported
                sl_price = params.pop('stopLossPrice', None)
                tp_price = params.pop('takeProfitPrice', None)
                
                order = ex.create_order(ccxt_symbol, order_type, side, amount, price, params)
                
                # If SL/TP provided, place them as separate reduce-only orders for Binance
                if (sl_price or tp_price) and exchange_name.lower() == 'binance':
                    try:
                        opposite_side = 'sell' if side.lower() == 'buy' else 'buy'
                        if sl_price:
                            ex.create_order(ccxt_symbol, 'STOP_MARKET', opposite_side, amount, None, {
                                'stopPrice': sl_price,
                                'reduceOnly': True
                            })
                            logger.info(f"[LIVE_SL] Stop Loss placed at {sl_price}")
                        if tp_price:
                            ex.create_order(ccxt_symbol, 'TAKE_PROFIT_MARKET', opposite_side, amount, None, {
                                'stopPrice': tp_price,
                                'reduceOnly': True
                            })
                            logger.info(f"[LIVE_TP] Take Profit placed at {tp_price}")
                    except Exception as e:
                        logger.error(f"Failed to attach SL/TP orders: {e}")

                return {
                    "success": True,
                    "execution_source": "live",
                    "exchange_status": "open",
                    "info": order.get('info', 'SUCCESS'),
                    "order_id": order.get('id')
                }
            except Exception as e:
                logger.error(f"Live order failed on {exchange_name}: {e}")
                return {"success": False, "error": str(e)}
        else:
            # Hard-Lock: Log but do not dispatch
            logger.info(f"[DISPATCH_LOCK_v1.9.4] {'LIVE_BLOCKED' if not is_simulated else 'SIM'} {exchange_name} | {side} {amount} {ccxt_symbol} | Type: {order_type} | Params: {params}")
            
            # Simulate success for the UI
            return {
                "success": True, 
                "execution_source": "simulated",
                "exchange_status": None,
                "info": "SIMULATED_SUCCESS_v1.9.4", 
                "order_id": f"sim_{exchange_name.lower()}_{int(time.time())}"
            }

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
                            "unrealizedPnl": p.get('unrealizedPnl'),
                            "notional": p.get('notional')
                        })
            except Exception as e:
                logger.error(f"Error fetching positions for {name}: {e}")
        return all_positions

    def close_position(self, exchange_name: str, symbol: str) -> Dict[str, Any]:
        """Exits a specific position by placing an opposite market order."""
        if exchange_name not in self.exchanges:
            return {"success": False, "error": f"Exchange {exchange_name} not initialized."}

        ex = self.exchanges[exchange_name]
        try:
            ex.load_markets()
            positions = ex.fetch_positions([symbol])
            
            target_pos = None
            for p in positions:
                if p['symbol'] == symbol or p['info'].get('symbol') == symbol:
                    if float(p.get('contracts', 0)) > 0:
                        target_pos = p
                        break
            
            if not target_pos:
                return {"success": False, "error": f"No active position found for {symbol} on {exchange_name}"}

            amount = float(target_pos['contracts'])
            side = target_pos['side']
            opposite_side = "sell" if side == "long" else "buy"

            logger.info(f"Closing {side} position for {symbol} on {exchange_name} (Amount: {amount})")
            return self.place_order(exchange_name, symbol, opposite_side, "market", amount)

        except Exception as e:
            logger.error(f"Failed to close position {symbol} on {exchange_name}: {e}")
            return {"success": False, "error": str(e)}

    def panic_sell_all(self) -> Dict[str, Any]:
        """Emergency exit: Closes ALL active positions across ALL exchanges."""
        positions = self.get_active_positions()
        if not positions:
            return {"success": True, "message": "No active positions to close."}

        results = []
        for p in positions:
            res = self.close_position(p['exchange'], p['symbol'])
            results.append({"symbol": p['symbol'], "exchange": p['exchange'], "result": res})

        success_count = sum(1 for r in results if r['result'].get('success'))
        return {
            "success": True,
            "total": len(positions),
            "closed": success_count,
            "details": results
        }

# Singleton manager
_hub_instance = None

def get_hub():
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = ExchangeHub()
    return _hub_instance
