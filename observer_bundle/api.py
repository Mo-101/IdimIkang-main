import asyncio
import json
import logging
import os
import select
import subprocess
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config

try:
    from sse_starlette.sse import EventSourceResponse
    HAS_SSE = True
except Exception:
    EventSourceResponse = StreamingResponse
    HAS_SSE = False


# ---------------------------------------------------------------------------
# Environment / config
# ---------------------------------------------------------------------------
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
PM2_SCANNER_NAME = os.environ.get("PM2_SCANNER_NAME", "idim-scanner")

CURRENT_LOGIC_VERSION = config.CURRENT_LOGIC_VERSION
CURRENT_CONFIG_VERSION = config.CURRENT_CONFIG_VERSION
START_TS = time.time()

logger = logging.getLogger("idim-api")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------------------------------------------------------------------------
# JSON-safe helpers
# ---------------------------------------------------------------------------
def _to_builtin(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (np.bool_,)):
        return bool(value)

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        return float(value)

    if isinstance(value, (np.ndarray,)):
        return value.tolist()

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_to_builtin(v) for v in value]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return str(value)


def _json_dumps_safe(value: Any) -> str:
    return json.dumps(_to_builtin(value), ensure_ascii=False)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def db_conn():
    return psycopg2.connect(DATABASE_URL)


def _query_one(cur, query: str, params: tuple = ()) -> Optional[dict]:
    cur.execute(query, params)
    row = cur.fetchone()
    return _to_builtin(row) if row else None


def _get_executor_hub():
    from executor import get_hub
    return get_hub()


# ---------------------------------------------------------------------------
# SSE broadcaster
# ---------------------------------------------------------------------------
class SignalBroadcaster:
    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        async with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    async def publish(self, payload: str):
        async with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass


broadcaster = SignalBroadcaster()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, cls=_NumpyEncoder)


class PgNotifyListener(threading.Thread):
    """Threaded PostgreSQL LISTEN/NOTIFY listener that fans out to SSE clients."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__(daemon=True)
        self.loop = loop
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        while not self.stop_event.is_set():
            conn = None
            cur = None
            try:
                conn = psycopg2.connect(DATABASE_URL)
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
                cur = conn.cursor()
                cur.execute("LISTEN new_signal;")
                logger.info("API listening for PostgreSQL channel 'new_signal'")

                while not self.stop_event.is_set():
                    ready = select.select([conn], [], [], 5)
                    if ready == ([], [], []):
                        continue

                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        payload = notify.payload
                        logger.info("Received new_signal notification (%d bytes)", len(payload))
                        asyncio.run_coroutine_threadsafe(broadcaster.publish(payload), self.loop)

            except Exception:
                logger.exception("PostgreSQL LISTEN loop failed; retrying in 2s")
                time.sleep(2)
            finally:
                try:
                    if cur:
                        cur.close()
                except Exception:
                    pass
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# App / lifecycle
# ---------------------------------------------------------------------------
app = FastAPI(title="Idim Ikang API", version="1.4.0")
router = APIRouter(prefix="/api")


@app.on_event("startup")
async def startup_event():
    app.state.ccxt_ok = False
    app.state.executor_ready = False
    app.state.executor_error = None
    app.state.pg_listener = None

    try:
        _get_executor_hub()
        app.state.ccxt_ok = True
        app.state.executor_ready = True
        logger.info("Sovereign Executor initialized successfully.")
    except Exception as e:
        app.state.executor_error = str(e)
        logger.exception("Sovereign Executor initialization failed")

    try:
        loop = asyncio.get_running_loop()
        listener = PgNotifyListener(loop)
        listener.start()
        app.state.pg_listener = listener
    except Exception:
        logger.exception("Failed to start PostgreSQL notify listener")


@app.on_event("shutdown")
async def shutdown_event():
    listener: Optional[PgNotifyListener] = getattr(app.state, "pg_listener", None)
    if listener:
        listener.stop()
        listener.join(timeout=2)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class TradeOrder(BaseModel):
    exchange: str
    symbol: str
    side: str
    order_type: str
    amount: float
    price: Optional[float] = None
    leverage: Optional[int] = None
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None


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
    mode: str


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------
@router.get("/health")
def health():
    listener = getattr(app.state, "pg_listener", None)
    return {
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "logic_version": CURRENT_LOGIC_VERSION,
        "config_version": CURRENT_CONFIG_VERSION,
        "ccxt_ok": getattr(app.state, "ccxt_ok", False),
        "executor_ready": getattr(app.state, "executor_ready", False),
        "executor_error": getattr(app.state, "executor_error", None),
        "pg_listener_alive": bool(listener and listener.is_alive()),
    }


@router.get("/status")
def status():
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        last_signal = _query_one(
            cur,
            """
            SELECT ts, pair, side, score, regime, signal_family
            FROM signals
            WHERE logic_version = %s
            ORDER BY ts DESC
            LIMIT 1
            """,
            (CURRENT_LOGIC_VERSION,),
        )

        last_log = _query_one(
            cur,
            "SELECT ts, level, event, details FROM system_logs ORDER BY ts DESC LIMIT 1",
        )

        def _safe_ts(query: str):
            try:
                row = _query_one(cur, query)
                return row["ts"] if row and row.get("ts") else None
            except Exception:
                return None

        funding_ts = _safe_ts("SELECT MAX(funding_time) AS ts FROM funding_rates")
        oi_ts = _safe_ts("SELECT MAX(timestamp) AS ts FROM open_interest")
        ls_ts = _safe_ts("SELECT MAX(timestamp) AS ts FROM ls_ratios")

        unresolved = _query_one(
            cur,
            "SELECT COUNT(*) AS unresolved FROM signals WHERE outcome IS NULL AND logic_version = %s",
            (CURRENT_LOGIC_VERSION,),
        )

    scanner_state = "unknown"
    try:
        res = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            pm2_json = json.loads(res.stdout)
            scanner_proc = next((p for p in pm2_json if p.get("name") == PM2_SCANNER_NAME), None)
            scanner_state = scanner_proc["pm2_env"]["status"] if scanner_proc else "stopped"
    except Exception:
        logger.exception("Failed to query PM2 status")

    return _to_builtin({
        "service": "idim-api",
        "scanner_state": scanner_state,
        "uptime_seconds": round(time.time() - START_TS, 1),
        "logic_version": CURRENT_LOGIC_VERSION,
        "config_version": CURRENT_CONFIG_VERSION,
        "last_signal": last_signal,
        "last_log": last_log,
        "freshness": {
            "funding": funding_ts,
            "oi": oi_ts,
            "ls": ls_ts,
            "unresolved_count": unresolved["unresolved"] if unresolved else 0,
        },
    })


@router.get("/signals")
def signals(all_history: bool = Query(False)):
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        query = "SELECT * FROM signals"
        params: tuple = ()
        if not all_history:
            query += " WHERE logic_version = %s"
            params = (CURRENT_LOGIC_VERSION,)
        query += " ORDER BY ts DESC LIMIT 100"

        cur.execute(query, params)
        rows = cur.fetchall()

    return {"count": len(rows), "signals": _to_builtin(rows)}


@router.get("/stats")
def stats(all_history: bool = Query(False)):
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        q = "SELECT outcome, execution_source, COUNT(*) as count FROM signals"
        params: tuple = ()
        if not all_history:
            q += " WHERE logic_version = %s"
            params = (CURRENT_LOGIC_VERSION,)
        q += " GROUP BY outcome, execution_source"
        cur.execute(q, params)
        res = cur.fetchall()

        unresolved_query = "SELECT COUNT(*) AS unresolved FROM signals WHERE outcome IS NULL"
        version_query = "SELECT logic_version, config_version FROM signals"
        latest_cycle_query = "SELECT details FROM system_logs WHERE event = 'scan_complete' ORDER BY ts DESC LIMIT 1"
        if not all_history:
            unresolved_query += " AND logic_version = %s"
            version_query += " WHERE logic_version = %s"
        version_query += " ORDER BY ts DESC LIMIT 1"

        cur.execute(unresolved_query, params)
        unresolved_row = cur.fetchone()

        cur.execute(version_query, params)
        version_row = cur.fetchone()

        cur.execute(latest_cycle_query)
        latest_cycle_row = cur.fetchone()

    stats_data = {
        "simulated": {"wins": 0, "losses": 0, "expired": 0, "total": 0},
        "live": {"wins": 0, "losses": 0, "expired": 0, "total": 0},
        "total": {"wins": 0, "losses": 0, "expired": 0, "total": 0},
    }

    for r in res:
        outcome = (r["outcome"] or "unresolved").lower()
        source = (r["execution_source"] or "simulated").lower()
        count = int(r["count"])

        if source not in ("simulated", "live"):
            source = "simulated"

        if outcome in ("partial_win", "live_partial", "win", "live_win"):
            mapped = "wins"
        elif outcome in ("loss", "live_loss"):
            mapped = "losses"
        elif outcome == "expired":
            mapped = "expired"
        else:
            continue

        stats_data[source][mapped] += count
        stats_data["total"][mapped] += count

        if mapped in ("wins", "losses"):
            stats_data[source]["total"] += count
            stats_data["total"]["total"] += count

    def calc_rates(d: dict) -> dict:
        total = d["total"]
        d["win_rate"] = round((d["wins"] / total * 100), 2) if total > 0 else 0.0
        d["profit_factor"] = round(d["wins"] / d["losses"], 2) if d["losses"] > 0 else (float(d["wins"]) if d["wins"] > 0 else 0.0)
        return d

    stats_data["simulated"] = calc_rates(stats_data["simulated"])
    stats_data["live"] = calc_rates(stats_data["live"])
    stats_data["total"] = calc_rates(stats_data["total"])
    stats_data["unresolved"] = int(unresolved_row["unresolved"]) if unresolved_row else 0

    if version_row:
        stats_data["logic_version"] = version_row.get("logic_version")
        stats_data["config_version"] = version_row.get("config_version")

    stats_data["latest_cycle"] = latest_cycle_row.get("details") if latest_cycle_row else {
        "signals_emitted": 0,
        "pairs_processed": 0,
        "setups_viable_pre_phase2": 0,
        "setups_blocked_phase2": 0,
    }

    return _to_builtin(stats_data)


@router.get("/cell-performance")
def cell_performance(all_history: bool = Query(False)):
    allowed_cells = [
        ("STRONG_UPTREND", 80), ("STRONG_UPTREND", 85), ("STRONG_UPTREND", 90),
        ("STRONG_DOWNTREND", 80), ("STRONG_DOWNTREND", 85),
    ]

    results: List[dict] = []
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for regime, bucket in allowed_cells:
            q = """
                SELECT outcome, COUNT(*) as c
                FROM signals
                WHERE regime = %s
                  AND (reason_trace->>'score_bucket')::int = %s
            """
            params: list[Any] = [regime, bucket]
            if not all_history:
                q += " AND logic_version = %s"
                params.append(CURRENT_LOGIC_VERSION)
            q += " GROUP BY outcome"

            cur.execute(q, tuple(params))
            counts = {r["outcome"] if r["outcome"] else "unresolved": int(r["c"]) for r in cur.fetchall()}

            wins = counts.get("win", 0) + counts.get("live_win", 0) + counts.get("partial_win", 0) + counts.get("live_partial", 0)
            losses = counts.get("loss", 0) + counts.get("live_loss", 0)
            expired = counts.get("expired", 0)

            wr = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0.0
            pf = round(wins / losses, 2) if losses > 0 else (float(wins) if wins > 0 else 0.0)

            results.append({
                "regime": regime,
                "score_bucket": bucket,
                "wins": wins,
                "losses": losses,
                "expired": expired,
                "win_rate": wr,
                "profit_factor": pf,
            })

    return _to_builtin(results)


# ---------------------------------------------------------------------------
# Real-time streaming
# ---------------------------------------------------------------------------
@router.get("/stream")
async def signal_stream(request: Request):
    async def event_generator():
        queue = await broadcaster.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    data = await asyncio.wait_for(queue.get(), timeout=20.0)
                    if HAS_SSE:
                        yield {"event": "new_signal", "data": data}
                    else:
                        yield f"event: new_signal\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    if HAS_SSE:
                        continue
                    else:
                        yield ": ping\n\n"
        finally:
            await broadcaster.unsubscribe(queue)

    if HAS_SSE:
        return EventSourceResponse(event_generator())
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/publish_signal")
async def publish_signal(signal: dict):
    clean_signal = _to_builtin(signal)
    payload = _json_dumps_safe(clean_signal)
    await broadcaster.publish(payload)
    return {"status": "published", "bytes": len(payload)}


# ---------------------------------------------------------------------------
# Trading execution endpoints
# ---------------------------------------------------------------------------
@router.get("/trade/exchanges")
def get_exchanges():
    try:
        hub = _get_executor_hub()
        exchanges = []
        for name, ex in hub.exchanges.items():
            exchanges.append({
                "name": name,
                "is_simulated": getattr(ex, "is_simulated", False),
            })
        return {"active_exchanges": _to_builtin(exchanges)}
    except Exception as e:
        logger.exception("Failed to get active exchanges")
        return {"active_exchanges": [], "error": str(e)}


@router.get("/trade/balances")
def get_balances():
    hub = _get_executor_hub()
    return {"balances": _to_builtin(hub.get_balances())}


@router.get("/trade/positions")
def get_positions():
    hub = _get_executor_hub()
    return {"positions": _to_builtin(hub.get_active_positions())}


@router.get("/market/ticker/{exchange}/{symbol}")
def get_ticker(exchange: str, symbol: str):
    hub = _get_executor_hub()
    data = hub.get_ticker_data(exchange, symbol)
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return _to_builtin(data)


@router.post("/trade/leverage")
def set_leverage(req: LeverageRequest):
    hub = _get_executor_hub()
    result = hub.set_leverage(req.exchange, req.symbol, req.leverage)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return _to_builtin(result)


@router.post("/trade/margin")
def set_margin(req: MarginRequest):
    hub = _get_executor_hub()
    result = hub.set_margin_mode(req.exchange, req.symbol, req.mode)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return _to_builtin(result)


@router.post("/trade/place")
def place_order(order: TradeOrder):
    hub = _get_executor_hub()

    if order.leverage:
        hub.set_leverage(order.exchange, order.symbol, order.leverage)

    params: Dict[str, Any] = {}
    if order.tp_price is not None:
        params["takeProfitPrice"] = order.tp_price
    if order.sl_price is not None:
        params["stopLossPrice"] = order.sl_price

    result = hub.place_order(
        exchange_name=order.exchange,
        symbol=order.symbol,
        side=order.side,
        order_type=order.order_type,
        amount=order.amount,
        price=order.price,
        params=params,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return _to_builtin(result)


@router.post("/trade/close")
def close_position(req: ClosePositionRequest):
    hub = _get_executor_hub()
    result = hub.close_position(req.exchange, req.symbol)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return _to_builtin(result)


@router.post("/trade/panic")
def panic_sell(req: PanicRequest):
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Panic confirmation missing")
    hub = _get_executor_hub()
    return _to_builtin(hub.panic_sell_all())


# ---------------------------------------------------------------------------
# Route registration / static files
# ---------------------------------------------------------------------------
app.include_router(router)

dist_path = Path(__file__).resolve().parent.parent / "dist"
if dist_path.is_dir():
    app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="static")
