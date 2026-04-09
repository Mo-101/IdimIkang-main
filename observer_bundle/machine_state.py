#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import psycopg2
import requests
from dotenv import load_dotenv

import exchange_discovery

load_dotenv()

DB = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang",
)
POSTFIX_TS = os.getenv("POSTFIX_TS", "2026-04-06 17:00:00+03")
OPPORTUNITY_WINDOW = int(os.getenv("OPPORTUNITY_WINDOW", "12"))
ENABLE_MARKET_DISPERSION = os.getenv("ENABLE_MARKET_DISPERSION", "false").strip().lower() in {
    "1",
    "true",
    "t",
    "yes",
    "y",
    "on",
}
DISPERSION_CAP = float(os.getenv("DISPERSION_CAP", "0.04"))
DISPERSION_UNIVERSE_SIZE = int(os.getenv("DISPERSION_UNIVERSE_SIZE", "30"))
BINANCE_FUTURES_URL = os.getenv("BINANCE_FUTURES_URL", "https://fapi.binance.com")


def db() -> psycopg2.extensions.connection:
    return psycopg2.connect(DB)


def scalar(conn: psycopg2.extensions.connection, q: str, params: Optional[dict] = None) -> Any:
    with conn.cursor() as cur:
        cur.execute(q, params or {})
        row = cur.fetchone()
        return row[0] if row else None


def fetchdf(conn: psycopg2.extensions.connection, q: str, params: Optional[dict] = None) -> pd.DataFrame:
    return pd.read_sql(q, conn, params=params)


def log_event(conn: psycopg2.extensions.connection, level: str, event: str, details: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO system_logs(level, component, event, details) VALUES (%s,%s,%s,%s::jsonb)",
            (level, "machine_state", event, json.dumps(details)),
        )
        conn.commit()


def heartbeat_age_seconds(conn: psycopg2.extensions.connection, component: str, event_like: str) -> float:
    q = """
    SELECT EXTRACT(EPOCH FROM (NOW() - MAX(ts)))
    FROM system_logs
    WHERE component = %(component)s
      AND event LIKE %(event)s
    """
    v = scalar(conn, q, {"component": component, "event": event_like})
    return float(v) if v is not None else 1e9


def _fetch_signals_df(conn: psycopg2.extensions.connection, base_query: str, params: dict) -> pd.DataFrame:
    try:
        return fetchdf(conn, base_query, params)
    except Exception:
        fallback = base_query.replace("AND source = 'observer_live'", "")
        return fetchdf(conn, fallback, params)


def integrity_score(conn: psycopg2.extensions.connection) -> Tuple[float, int, int]:
    q = """
    SELECT outcome, side, adverse_excursion
    FROM signals
    WHERE ts >= %(postfix)s
      AND outcome IN ('LOSS','WIN','PARTIAL_WIN')
      AND source = 'observer_live'
      AND source != 'pre_fix_legacy'
    """
    df = _fetch_signals_df(conn, q, {"postfix": POSTFIX_TS})
    if df.empty:
        return 1.0, 0, 0

    bad = 0
    n = len(df)
    for _, r in df.iterrows():
        if r["outcome"] == "LOSS":
            ae = r.get("adverse_excursion")
            if ae is not None and float(ae) < 0.999:
                bad += 1
    I = 1.0 - (bad / max(n, 1))
    return I, bad, n


def edge_estimate(conn: psycopg2.extensions.connection) -> Tuple[float, int, int, int]:
    q = """
    SELECT r_multiple
    FROM signals
    WHERE ts >= %(postfix)s
      AND source = 'observer_live'
      AND outcome IN ('WIN','LOSS','PARTIAL_WIN')
      AND r_multiple IS NOT NULL
    """
    df = _fetch_signals_df(conn, q, {"postfix": POSTFIX_TS})
    if df.empty:
        return 0.0, 0, 0, 0

    r = df["r_multiple"].astype(float)
    wins = r[r > 0]
    losses = r[r < 0]

    W = len(wins)
    L = len(losses)
    p = (W + 1) / (W + L + 2)

    avg_win = float(wins.mean()) if W else 0.0
    avg_loss = abs(float(losses.mean())) if L else 1.0

    E = p * avg_win - (1 - p) * avg_loss
    return E, len(r), W, L


def active_positions(conn: psycopg2.extensions.connection) -> int:
    q = "SELECT COUNT(*) FROM signals WHERE outcome IS NULL"
    return int(scalar(conn, q) or 0)


def opportunity_flow(conn: psycopg2.extensions.connection) -> float:
    q = """
    SELECT ts, details
    FROM system_logs
    WHERE component = 'scanner'
      AND event = 'scan_complete'
    ORDER BY ts DESC
    LIMIT %(limit)s
    """
    df = fetchdf(conn, q, {"limit": OPPORTUNITY_WINDOW})
    if df.empty:
        return 0.0

    oc: List[float] = []
    osig: List[float] = []
    for _, r in df.iterrows():
        details = r["details"]
        payload = details if isinstance(details, dict) else json.loads(details or "{}")
        u = max(int(payload.get("universe") or payload.get("symbol_count") or 1), 1)
        c = int(payload.get("candidates") or 0)
        s = int(payload.get("fired") or payload.get("signals") or 0)
        oc.append(c / u)
        osig.append(s / u)
    return 0.6 * sum(oc) / len(oc) + 0.4 * sum(osig) / len(osig)


def fetch_4h_return(symbol: str) -> Optional[float]:
    try:
        resp = requests.get(
            f"{BINANCE_FUTURES_URL}/fapi/v1/klines",
            params={"symbol": symbol, "interval": "4h", "limit": 2},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 2:
            return None
        prev_close = float(data[-2][4])
        last_close = float(data[-1][4])
        if prev_close <= 0:
            return None
        return (last_close - prev_close) / prev_close
    except Exception:
        return None


def macro_risk_pressure() -> Tuple[float, List[str]]:
    if not ENABLE_MARKET_DISPERSION:
        return 0.0, ["market dispersion disabled"]

    notes: List[str] = []
    universe = exchange_discovery.get_top_liquid_symbols(limit=DISPERSION_UNIVERSE_SIZE)
    if "BTCUSDT" not in universe:
        universe = ["BTCUSDT"] + universe

    btc_return = fetch_4h_return("BTCUSDT")
    if btc_return is None:
        return 0.0, ["btc return unavailable"]

    returns: List[float] = []
    for symbol in universe:
        if symbol == "BTCUSDT":
            continue
        r = fetch_4h_return(symbol)
        if r is not None:
            returns.append(r)

    if not returns:
        return 0.0, ["alt returns unavailable"]

    dispersion = median([abs(r - btc_return) for r in returns])
    R = min(dispersion / DISPERSION_CAP, 1.0)
    if R >= 0.8:
        notes.append("alt dispersion elevated")
    return R, notes


def state_packet() -> Dict[str, Any]:
    conn = db()
    try:
        t_s = heartbeat_age_seconds(conn, "scanner", "scan_complete%")
        t_o = heartbeat_age_seconds(conn, "outcome_tracker", "tracker_run_complete%")
        t_l = heartbeat_age_seconds(conn, "trade_learner", "trade_learner_started%")

        h_s = 1 if t_s <= 600 else 0
        h_o = 1 if t_o <= 120 else 0
        h_l = 1 if t_l <= 120 else 0
        H = (h_s + h_o + h_l) / 3

        I, bad, n_integrity = integrity_score(conn)
        E, n_resolved, wins, losses = edge_estimate(conn)
        A = active_positions(conn)
        O = opportunity_flow(conn)

        R, risk_notes = macro_risk_pressure()
        m = max(0.25, 1 - 0.75 * R)

        if H < 1.0:
            state = "BROKEN"
        elif I < 0.95:
            state = "DEGRADED_INTEGRITY"
        elif A == 0 and n_resolved < 30:
            state = "FLAT_LEARNING"
        elif A > 0 and n_resolved < 30:
            state = "ACTIVE_LEARNING"
        elif E <= 0:
            state = "DEGRADED_EDGE"
        elif A == 0:
            state = "FLAT_READY"
        else:
            state = "ACTIVE_READY"

        notes: List[str] = []
        if H == 1.0:
            notes.append("all services fresh")
        else:
            notes.append("service heartbeat stale")
        if I < 0.95:
            notes.append("outcome integrity below target")
        if n_resolved < 30:
            notes.append("learning sample small")
        if A == 0:
            notes.append("no open positions")
        notes.extend(risk_notes)

        packet = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "state": state,
            "H": round(H, 4),
            "I": round(I, 4),
            "O": round(O, 4),
            "E": round(E, 4),
            "R": round(R, 4),
            "A": A,
            "size_multiplier": round(m, 4),
            "resolved_postfix": n_resolved,
            "integrity_bad": bad,
            "integrity_n": n_integrity,
            "wins": wins,
            "losses": losses,
            "ready_to_tune": bool(n_resolved >= 30 and I >= 0.98),
            "notes": notes,
        }
        log_event(conn, "INFO", "machine_state_tick", packet)
        return packet
    finally:
        conn.close()


if __name__ == "__main__":
    print(json.dumps(state_packet(), indent=2))
