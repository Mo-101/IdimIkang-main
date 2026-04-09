#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
POLL_SECONDS = int(os.environ.get("TRADE_LEARNER_POLL_SECONDS", "30"))
BATCH_SIZE = int(os.environ.get("TRADE_LEARNER_BATCH_SIZE", "25"))

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://10.255.255.254:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi4")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "90"))

NEO4J_HTTP_URL = os.environ.get("NEO4J_HTTP_URL", "http://localhost:7474/db/neo4j/tx/commit")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
REQUESTS_SESSION = requests.Session()
REQUESTS_SESSION.trust_env = False


def db_conn():
    return psycopg2.connect(DATABASE_URL)


def log_event(level: str, event: str, details: Dict[str, Any]) -> None:
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO system_logs(level, component, event, details) VALUES (%s,%s,%s,%s::jsonb)",
            (level, "trade_learner", event, json.dumps(details, default=str)),
        )
        conn.commit()


def ensure_schema() -> None:
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("ALTER TABLE signals ADD COLUMN IF NOT EXISTS lesson TEXT")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_aggregates (
                regime VARCHAR(20) NOT NULL,
                score_bucket INT NOT NULL,
                side VARCHAR(5) NOT NULL,
                total_trades INT NOT NULL DEFAULT 0,
                wins INT NOT NULL DEFAULT 0,
                losses INT NOT NULL DEFAULT 0,
                partial_wins INT NOT NULL DEFAULT 0,
                total_r NUMERIC NOT NULL DEFAULT 0,
                profit_factor NUMERIC,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS signal_aggregates_unique ON signal_aggregates (regime, score_bucket, side)"
        )
        conn.commit()


def fetch_pending_resolved(limit: int) -> list[dict]:
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, signal_id, pair, side, entry, stop_loss, take_profit, score, regime,
                   reason_trace, outcome, r_multiple, adverse_excursion, ts, updated_at
            FROM signals
            WHERE outcome IS NOT NULL
              AND lesson IS NULL
            ORDER BY updated_at ASC NULLS LAST, id ASC
            LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())


def extract_volume_ratio(reason_trace: Any) -> Optional[float]:
    if not isinstance(reason_trace, dict):
        return None
    value = reason_trace.get("volume_ratio")
    try:
        return float(value) if value is not None else None
    except Exception:
        return None


def extract_market_context(reason_trace: Any) -> tuple[str, str, str]:
    if not isinstance(reason_trace, dict):
        return "unknown", "unknown", "unknown"
    btc_regime = reason_trace.get("btc_regime")
    gate_snapshot = reason_trace.get("gate_snapshot")
    if not btc_regime and isinstance(gate_snapshot, dict):
        btc_regime = gate_snapshot.get("btc_regime")
    funding = reason_trace.get("funding") or reason_trace.get("funding_rate") or "unknown"
    ls_ratio = reason_trace.get("ls_ratio") or reason_trace.get("long_short_ratio") or "unknown"
    return str(btc_regime or "unknown"), str(funding), str(ls_ratio)


def extract_gate_reasons(reason_trace: Any) -> tuple[str, str]:
    if not isinstance(reason_trace, dict):
        return "[]", "[]"
    gates = reason_trace.get("gate_snapshot") or reason_trace.get("gates")
    if not isinstance(gates, dict):
        return "[]", "[]"
    reasons_pass = [k for k, v in gates.items() if isinstance(v, bool) and v]
    reasons_fail = [k for k, v in gates.items() if isinstance(v, bool) and not v]
    return json.dumps(reasons_pass), json.dumps(reasons_fail)


def score_bucket(value: Any) -> int:
    try:
        bucket = int(float(value) // 10) * 10
        return max(bucket, 0)
    except Exception:
        return 0


def validate_trade_integrity(trade: dict) -> tuple[bool, str]:
    outcome = str(trade.get("outcome") or "").upper()
    adverse_excursion = trade.get("adverse_excursion")

    if outcome == "LOSS" and adverse_excursion is not None:
        try:
            ae = float(adverse_excursion)
            if ae < 0.999:
                return False, f"LOSS_WITH_SUB_1R_AE ({ae:.6f})"
        except Exception:
            return False, "LOSS_WITH_INVALID_AE"

    return True, "OK"


def build_prompt(trade: dict) -> str:
    pair = trade.get("pair")
    side = trade.get("side")
    regime = trade.get("regime")
    outcome = trade.get("outcome")
    r_multiple = trade.get("r_multiple")
    score = trade.get("score")
    reason_trace = trade.get("reason_trace") if isinstance(trade.get("reason_trace"), dict) else {}
    reasons_pass, reasons_fail = extract_gate_reasons(reason_trace)
    btc_regime, funding, ls_ratio = extract_market_context(reason_trace)

    prompt = f"""
You are the Mind of MoStar. Analyze this trade:

Pair: {pair}, Side: {side}, Outcome: {outcome}, R: {r_multiple}
Regime: {regime}, Score: {score}
Reason trace: {reasons_pass} / {reasons_fail}
Market context: BTC regime {btc_regime}, funding {funding}, LS ratio {ls_ratio}

Write a concise lesson (max 100 words) and suggest one weight adjustment in JSON:
{{"lesson": "...", "weight_adjustment": {{"indicator": "RSI", "delta": +2}}}}
""".strip()

    return prompt


def call_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    url = f"{OLLAMA_BASE_URL}/api/generate"
    resp = REQUESTS_SESSION.post(url, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()
    return str(data.get("response") or "").strip()


def parse_lesson_response(raw: str) -> dict:
    if not raw:
        return {
            "lesson": "No lesson generated",
            "weight_indicator": "",
            "weight_delta": 0.0,
            "weight_adjustment": {},
            "raw": raw,
        }

    candidate = raw
    if not raw.strip().startswith("{"):
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            candidate = m.group(0)

    try:
        parsed = json.loads(candidate)
        lesson = str(parsed.get("lesson") or "No lesson generated").strip()
        weight_adjustment = parsed.get("weight_adjustment") or {}
        if not isinstance(weight_adjustment, dict):
            weight_adjustment = {}
        indicator = str(weight_adjustment.get("indicator") or "").strip()
        delta_raw = weight_adjustment.get("delta", 0.0)
        try:
            delta = float(delta_raw)
        except Exception:
            delta = 0.0
        return {
            "lesson": lesson,
            "weight_indicator": indicator,
            "weight_delta": delta,
            "weight_adjustment": weight_adjustment,
            "raw": raw,
        }
    except Exception:
        return {
            "lesson": raw[:500],
            "weight_indicator": "",
            "weight_delta": 0.0,
            "weight_adjustment": {},
            "raw": raw,
        }


def write_mostar_moment(trade: dict, lesson_data: dict) -> None:
    signal_id = str(trade.get("signal_id"))
    btc_regime, funding, ls_ratio = extract_market_context(trade.get("reason_trace"))

    cypher = """
    MERGE (s:Signal {signal_id: $signal_id})
    MERGE (m:TradeLesson:SoulLayer:MoStarMoment {signal_id: $signal_id})
    SET m.pair = $pair,
        m.side = $side,
        m.regime = $regime,
        m.outcome = $outcome,
        m.r_multiple = $r_multiple,
        m.score = $score,
        m.volume_ratio = $volume_ratio,
        m.btc_regime = $btc_regime,
        m.funding = $funding,
        m.ls_ratio = $ls_ratio,
        m.lesson = $lesson,
        m.weight_indicator = $weight_indicator,
        m.weight_delta = $weight_delta,
        m.weight_adjustment = $weight_adjustment,
        m.ts = $ts,
        m.created_at = datetime($created_at)
    MERGE (s)-[:BECAME]->(m)
    """

    params = {
        "signal_id": signal_id,
        "pair": trade.get("pair"),
        "side": trade.get("side"),
        "regime": trade.get("regime"),
        "outcome": trade.get("outcome"),
        "r_multiple": float(trade.get("r_multiple") or 0.0),
        "score": float(trade.get("score") or 0.0),
        "volume_ratio": extract_volume_ratio(trade.get("reason_trace")),
        "btc_regime": btc_regime,
        "funding": funding,
        "ls_ratio": ls_ratio,
        "lesson": lesson_data.get("lesson"),
        "weight_indicator": lesson_data.get("weight_indicator"),
        "weight_delta": float(lesson_data.get("weight_delta") or 0.0),
        "weight_adjustment": json.dumps(lesson_data.get("weight_adjustment") or {}),
        "ts": str(trade.get("ts")),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    payload = {
        "statements": [
            {
                "statement": cypher,
                "parameters": params,
            }
        ]
    }

    resp = REQUESTS_SESSION.post(
        NEO4J_HTTP_URL,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    errors = body.get("errors") or []
    if errors:
        raise RuntimeError(f"Neo4j error: {errors}")


def persist_lesson_to_signal(signal_db_id: int, lesson_data: dict) -> None:
    lesson_text = lesson_data.get("lesson") or "No lesson generated"
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE signals SET lesson = %s, updated_at = NOW() WHERE id = %s",
            (lesson_text, signal_db_id),
        )
        conn.commit()


def compute_aggregate_metrics(regime: str, side: str, bucket: int) -> Optional[dict]:
    with db_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_trades,
                COUNT(*) FILTER (WHERE outcome = 'WIN') AS wins,
                COUNT(*) FILTER (WHERE outcome = 'LOSS') AS losses,
                COUNT(*) FILTER (WHERE outcome = 'PARTIAL_WIN') AS partial_wins,
                COALESCE(SUM(r_multiple), 0) AS total_r,
                CASE
                    WHEN SUM(CASE WHEN r_multiple < 0 THEN -r_multiple ELSE 0 END) = 0 THEN NULL
                    ELSE SUM(CASE WHEN r_multiple > 0 THEN r_multiple ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN r_multiple < 0 THEN -r_multiple ELSE 0 END), 0)
                END AS profit_factor
            FROM signals
            WHERE outcome IS NOT NULL
              AND regime = %s
              AND side = %s
              AND COALESCE(score, 0) >= %s
              AND COALESCE(score, 0) < %s
            """,
            (regime, side, bucket, bucket + 10),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def upsert_signal_aggregate(regime: str, side: str, bucket: int, metrics: dict) -> None:
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO signal_aggregates (
                regime, score_bucket, side, total_trades, wins, losses, partial_wins, total_r, profit_factor, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (regime, score_bucket, side) DO UPDATE
            SET total_trades = EXCLUDED.total_trades,
                wins = EXCLUDED.wins,
                losses = EXCLUDED.losses,
                partial_wins = EXCLUDED.partial_wins,
                total_r = EXCLUDED.total_r,
                profit_factor = EXCLUDED.profit_factor,
                updated_at = NOW()
            """,
            (
                regime,
                bucket,
                side,
                int(metrics.get("total_trades") or 0),
                int(metrics.get("wins") or 0),
                int(metrics.get("losses") or 0),
                int(metrics.get("partial_wins") or 0),
                float(metrics.get("total_r") or 0.0),
                metrics.get("profit_factor"),
            ),
        )
        conn.commit()


def update_signal_aggregates(trade: dict) -> None:
    regime = trade.get("regime")
    side = trade.get("side")
    bucket = score_bucket(trade.get("score"))
    if not regime or not side:
        log_event(
            "WARNING",
            "aggregate_skipped_missing_context",
            {"signal_id": trade.get("signal_id"), "regime": regime, "side": side},
        )
        return
    metrics = compute_aggregate_metrics(str(regime), str(side), bucket)
    if not metrics:
        log_event(
            "WARNING",
            "aggregate_missing_metrics",
            {"signal_id": trade.get("signal_id"), "regime": regime, "side": side, "bucket": bucket},
        )
        return
    upsert_signal_aggregate(str(regime), str(side), bucket, metrics)
    log_event(
        "INFO",
        "aggregate_updated",
        {"signal_id": trade.get("signal_id"), "regime": regime, "side": side, "bucket": bucket},
    )


def mark_skipped(signal_db_id: int, reason: str) -> None:
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE signals SET lesson = %s, updated_at = NOW() WHERE id = %s",
            (f"SKIPPED:{reason}", signal_db_id),
        )
        conn.commit()


def process_trade(trade: dict) -> None:
    signal_id = str(trade.get("signal_id"))
    ok, integrity_reason = validate_trade_integrity(trade)

    if not ok:
        mark_skipped(int(trade["id"]), integrity_reason)
        log_event(
            "WARNING",
            "trade_skipped_integrity",
            {"signal_id": signal_id, "reason": integrity_reason},
        )
        return

    prompt = build_prompt(trade)
    raw = call_ollama(prompt)
    lesson_data = parse_lesson_response(raw)

    write_mostar_moment(trade, lesson_data)
    persist_lesson_to_signal(int(trade["id"]), lesson_data)
    update_signal_aggregates(trade)

    log_event(
        "INFO",
        "trade_lesson_written",
        {
            "signal_id": signal_id,
            "pair": trade.get("pair"),
            "outcome": trade.get("outcome"),
            "weight_indicator": lesson_data.get("weight_indicator"),
            "weight_delta": lesson_data.get("weight_delta"),
        },
    )


def run_once() -> int:
    ensure_schema()
    rows = fetch_pending_resolved(BATCH_SIZE)
    if not rows:
        return 0

    processed = 0
    for row in rows:
        signal_id = str(row.get("signal_id"))
        try:
            process_trade(row)
            processed += 1
        except Exception as exc:
            log_event(
                "ERROR",
                "trade_lesson_error",
                {
                    "signal_id": signal_id,
                    "error": str(exc),
                },
            )
    return processed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    if args.loop:
        log_event("INFO", "trade_learner_started", {"poll_seconds": POLL_SECONDS, "batch_size": BATCH_SIZE, "model": OLLAMA_MODEL})
        while True:
            try:
                processed = run_once()
                log_event("INFO", "trade_learner_tick", {"processed": processed})
            except Exception as exc:
                log_event("ERROR", "trade_learner_loop_error", {"error": str(exc)})
            time.sleep(POLL_SECONDS)
    else:
        processed = run_once()
        log_event("INFO", "trade_learner_once", {"processed": processed})


if __name__ == "__main__":
    main()
