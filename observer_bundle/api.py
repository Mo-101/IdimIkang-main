import os
import json
import subprocess
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

import psycopg2
import psycopg2.extras
import config
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from executor import get_hub  # Lazy accessor

load_dotenv()

CURRENT_LOGIC_VERSION = config.CURRENT_LOGIC_VERSION
CURRENT_CONFIG_VERSION = config.CURRENT_CONFIG_VERSION
DATABASE_URL = os.environ["DATABASE_URL"]
PM2_SCANNER_NAME = os.environ.get("PM2_SCANNER_NAME", "idim-scanner")
START_TS = time.time()

app = FastAPI(title="Idim Ikang API", version="1.3.0")
router = APIRouter(prefix="/api")

# Startup lifecycle for dependency initialization
@app.on_event("startup")
async def startup_event():
    try:
        hub = get_hub()
        app.state.ccxt_ok = True
        app.state.executor_ready = True
        app.state.executor_error = None
        print("Sovereign Executor initialized successfully via ccxt.")
    except Exception as e:
        app.state.ccxt_ok = False
        app.state.executor_ready = False
        app.state.executor_error = str(e)
        print(f"Sovereign Executor initialization FAILED: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def db_conn():
    return psycopg2.connect(DATABASE_URL)

@router.get("/health")
def health():
    return {
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "logic_version": CURRENT_LOGIC_VERSION,
        "ccxt_ok": getattr(app.state, "ccxt_ok", False),
        "executor_ready": getattr(app.state, "executor_ready", False),
        "executor_error": getattr(app.state, "executor_error", None)
    }

@router.get("/status")
def status():
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT ts, pair, side, score, regime FROM signals WHERE logic_version = %s ORDER BY ts DESC LIMIT 1", (CURRENT_LOGIC_VERSION,))
        last_signal = cur.fetchone()
        
        cur.execute("SELECT ts, level, event, details FROM system_logs ORDER BY ts DESC LIMIT 1")
        last_log = cur.fetchone()
        
        # Freshness Stats
        cur.execute("SELECT MAX(funding_time) as ts FROM funding_rates")
        last_funding = cur.fetchone()
        cur.execute("SELECT MAX(timestamp) as ts FROM open_interest")
        last_oi = cur.fetchone()
        cur.execute("SELECT MAX(timestamp) as ts FROM ls_ratios")
        last_ls = cur.fetchone()
        cur.execute("SELECT COUNT(*) as count FROM signals WHERE outcome IS NULL AND logic_version = %s", (CURRENT_LOGIC_VERSION,))
        unresolved = cur.fetchone()
        
        scanner_state = "offline"
        try:
            res = subprocess.run(["pm2", "jlist"], capture_output=True, text=True)
            pm2_json = json.loads(res.stdout)
            scanner_proc = next((p for p in pm2_json if p.get("name") == PM2_SCANNER_NAME), None)
            scanner_state = scanner_proc["pm2_env"]["status"] if scanner_proc else "stopped"
        except:
            pass

    return {
        "service": "idim-api",
        "scanner_state": scanner_state,
        "uptime_seconds": round(time.time() - START_TS, 1),
        "logic_version": CURRENT_LOGIC_VERSION,
        "last_signal": last_signal,
        "last_log": last_log,
        "freshness": {
            "funding": last_funding["ts"].isoformat() if last_funding and last_funding["ts"] else None,
            "oi": last_oi["ts"].isoformat() if last_oi and last_oi["ts"] else None,
            "ls": last_ls["ts"].isoformat() if last_ls and last_ls["ts"] else None,
            "unresolved_count": unresolved["count"] if unresolved else 0
        }
    }

@router.get("/signals")
def signals(all_history: bool = Query(False)):
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        query = "SELECT * FROM signals"
        if not all_history:
            query += " WHERE logic_version = %s"
        query += " ORDER BY ts DESC LIMIT 100"
        
        if all_history:
            cur.execute(query)
        else:
            cur.execute(query, (CURRENT_LOGIC_VERSION,))
        rows = cur.fetchall()
    return {"count": len(rows), "signals": rows}

@router.get("/stats")
def stats(all_history: bool = Query(False)):
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        q = "SELECT outcome, COUNT(*) as count FROM signals"
        if not all_history:
            q += " WHERE logic_version = %s"
        q += " GROUP BY outcome"
        
        if all_history:
            cur.execute(q)
        else:
            cur.execute(q, (CURRENT_LOGIC_VERSION,))
        
        res = cur.fetchall()
        counts = {r['outcome'].lower() if r['outcome'] else 'unresolved': r['count'] for r in res}
        
        wins = counts.get('win', 0)
        losses = counts.get('loss', 0)
        expired = counts.get('expired', 0)
        total = wins + losses
        win_rate = round((wins / total * 100), 2) if total > 0 else 0
        pf = round(wins/losses, 2) if losses > 0 else (wins if wins > 0 else 0)

    return {
        "wins": wins,
        "losses": losses,
        "expired": expired,
        "unresolved": counts.get('unresolved', 0),
        "win_rate": win_rate,
        "profit_factor": pf
    }

@router.get("/cell-performance")
def cell_performance(all_history: bool = Query(False)):
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        allowed_cells = [
            ("STRONG_UPTREND", 80), ("STRONG_UPTREND", 85), ("STRONG_UPTREND", 90),
            ("STRONG_DOWNTREND", 80), ("STRONG_DOWNTREND", 85)
        ]
        results = []
        for regime, bucket in allowed_cells:
            q = "SELECT outcome, COUNT(*) as c FROM signals WHERE regime = %s AND (reason_trace->>'score_bucket')::int = %s"
            params = [regime, bucket]
            if not all_history:
                q += " AND logic_version = %s"
                params.append(CURRENT_LOGIC_VERSION)
            q += " GROUP BY outcome"
            cur.execute(q, tuple(params))
            counts = {r['outcome'] if r['outcome'] else 'unresolved': r['c'] for r in cur.fetchall()}
            
            w, l = counts.get('win', 0), counts.get('loss', 0)
            wr = round(w/(w+l)*100, 1) if (w+l)>0 else 0
            pf = round(w/l, 2) if l>0 else (w if w>0 else 0)
            results.append({
                "regime": regime, "score_bucket": bucket,
                "wins": w, "losses": l, "expired": counts.get('expired', 0),
                "win_rate": wr, "profit_factor": pf
            })
    return results

# === TRADING EXECUTION ENDPOINTS ===
class TradeOrder(BaseModel):
    exchange: str
    symbol: str
    side: str
    order_type: str
    amount: float
    price: float = None
    leverage: int = None
    tp_price: float = None
    sl_price: float = None

class ClosePositionRequest(BaseModel):
    exchange: str
    symbol: str

class PanicRequest(BaseModel):
    confirm: bool

class LeverageRequest(BaseModel):
    exchange: str
    symbol: str
    leverage: int

class MarginRequest(BaseModel):
    exchange: str
    symbol: str
    mode: str  # 'isolated' or 'cross'

@router.get("/trade/exchanges")
def get_exchanges():
    try:
        hub = get_hub()
        exchanges = []
        for name, ex in hub.exchanges.items():
            exchanges.append({
                "name": name,
                "is_simulated": getattr(ex, "is_simulated", False)
            })
        return {"active_exchanges": exchanges}
    except Exception as e:
        return {"active_exchanges": [], "error": str(e)}

@router.get("/trade/balances")
def get_balances():
    hub = get_hub()
    return {"balances": hub.get_balances()}

@router.get("/trade/positions")
def get_positions():
    hub = get_hub()
    return {"positions": hub.get_active_positions()}

@router.get("/market/ticker/{exchange}/{symbol}")
def get_ticker(exchange: str, symbol: str):
    hub = get_hub()
    data = hub.get_ticker_data(exchange, symbol)
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return data

@router.post("/trade/leverage")
def set_leverage(req: LeverageRequest):
    hub = get_hub()
    result = hub.set_leverage(req.exchange, req.symbol, req.leverage)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.post("/trade/margin")
def set_margin(req: MarginRequest):
    hub = get_hub()
    result = hub.set_margin_mode(req.exchange, req.symbol, req.mode)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.post("/trade/place")
def place_order(order: TradeOrder):
    hub = get_hub()
    
    # Handle leverage sync if provided
    if order.leverage:
        hub.set_leverage(order.exchange, order.symbol, order.leverage)
        
    # Build params for TP/SL if provided
    params = {}
    if order.tp_price:
        params['takeProfitPrice'] = order.tp_price
    if order.sl_price:
        params['stopLossPrice'] = order.sl_price

    result = hub.place_order(
        exchange_name=order.exchange,
        symbol=order.symbol,
        side=order.side,
        order_type=order.order_type,
        amount=order.amount,
        price=order.price,
        params=params
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.post("/api/trade/close")
@router.post("/trade/close")
def close_position(req: ClosePositionRequest):
    hub = get_hub()
    result = hub.close_position(req.exchange, req.symbol)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.post("/api/trade/panic")
@router.post("/trade/panic")
def panic_sell(req: PanicRequest):
    if not req.confirm:
         raise HTTPException(status_code=400, detail="Panic confirmation missing")
    hub = get_hub()
    return hub.panic_sell_all()

# === REGISTER ROUTES ===
app.include_router(router)

# === FALLBACK UI SERVING ===
# Serve the built Vite frontend if the static dist folder exists
dist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist"))
if os.path.isdir(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")
