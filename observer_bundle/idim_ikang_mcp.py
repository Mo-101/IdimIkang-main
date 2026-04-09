"""
idim_ikang_mcp.py — Sovereign Intelligence MCP Server
The Flame Architect | MoStar Industries | African Flame Initiative

Exposes Idim Ikang v1.5 signal intelligence via MCP protocol.
Connect from Claude, Windsurf, or any MCP-capable client.

Usage:
  python idim_ikang_mcp.py

Add to claude_desktop_config.json:
  {
    "mcpServers": {
      "idim_ikang": {
        "command": "python",
        "args": ["/path/to/idim_ikang_mcp.py"],
        "env": {
          "DB_URL": "postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang"
        }
      }
    }
  }
"""

import os
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ─── Constants ──────────────────────────────────────────────────────────────
DB_URL = os.getenv(
    "DB_URL",
    "postgresql://postgres:IdimIkangLocal2026!@localhost:5432/idim_ikang",
)
SERVER_VERSION = "v1.5-quant-alpha"


# ─── DB helpers ─────────────────────────────────────────────────────────────
def _get_conn():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def _query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]


def _fmt_ts(ts) -> str:
    if ts is None:
        return "—"
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%d %H:%M UTC")
    return str(ts)


# ─── Server ──────────────────────────────────────────────────────────────────
mcp = FastMCP("idim_ikang_mcp")


# ─── Input models ────────────────────────────────────────────────────────────
class SignalsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    limit: int = Field(default=10, ge=1, le=50, description="Number of signals to return (1–50)")
    outcome_filter: Optional[str] = Field(
        default=None,
        description="Filter by outcome: WIN, LOSS, PARTIAL_WIN, PERSISTING, or None for all",
    )
    pair: Optional[str] = Field(default=None, description="Filter by pair e.g. ETHUSDT")


class PerformanceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    source_filter: str = Field(
        default="observer_live",
        description="'observer_live' for v1.5 signals only, 'all' for everything",
    )


class GateStatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    tail_lines: int = Field(
        default=200, ge=50, le=1000,
        description="How many scanner log lines to scan for gate rejection summary",
    )


class LessonsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    limit: int = Field(default=5, ge=1, le=20, description="Number of trade lessons to return")


# ─── Tools ───────────────────────────────────────────────────────────────────

@mcp.tool(
    name="idim_get_signals",
    annotations={
        "title": "Get Idim Ikang Signals",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def idim_get_signals(params: SignalsInput) -> str:
    """Retrieve recent signals from Idim Ikang v1.5 sovereign signal engine.

    Returns signal details including pair, side, score, regime, entry/stop/TP levels,
    current outcome, R-multiple, and volume ratio.

    Args:
        params (SignalsInput): Filter options:
            - limit (int): Number of signals (default 10, max 50)
            - outcome_filter (str): Filter by WIN/LOSS/PARTIAL_WIN/PERSISTING/None
            - pair (str): Filter by specific pair e.g. ETHUSDT

    Returns:
        str: Markdown-formatted signal table with performance summary
    """
    where_clauses = ["source = 'observer_live'"]
    args: List[Any] = []

    if params.outcome_filter:
        where_clauses.append("outcome = %s")
        args.append(params.outcome_filter.upper())

    if params.pair:
        where_clauses.append("pair = %s")
        args.append(params.pair.upper())

    where = " AND ".join(where_clauses)
    sql = f"""
        SELECT pair, side, score, regime, ts, outcome, r_multiple,
               entry, stop_loss, take_profit,
               reason_trace->>'volume_ratio' AS vol_ratio,
               reason_trace->>'score_bucket' AS score_bucket,
               lesson
        FROM signals
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT %s
    """
    args.append(params.limit)

    try:
        rows = _query(sql, tuple(args))
    except Exception as e:
        return f"Error querying signals: {e}"

    if not rows:
        return "No signals found matching the criteria."

    lines = [f"## Idim Ikang Signals ({SERVER_VERSION})\n"]
    for r in rows:
        outcome_emoji = {
            "WIN": "✅", "PARTIAL_WIN": "🟡", "LOSS": "❌",
            "PERSISTING": "🔄", None: "⏳"
        }.get(r.get("outcome"), "❓")

        r_str = f"{r['r_multiple']:+.1f}R" if r.get("r_multiple") is not None else "open"
        vol = f"{float(r['vol_ratio']):.2f}x" if r.get("vol_ratio") else "—"

        lines.append(
            f"**{r['pair']}** {r['side']} | Score: {r['score']} | Regime: {r['regime']}\n"
            f"  Entry: {r['entry']} | SL: {r['stop_loss']:.4f} | TP: {r['take_profit']:.4f}\n"
            f"  Vol: {vol} | Outcome: {outcome_emoji} {r.get('outcome') or 'OPEN'} ({r_str})\n"
            f"  Fired: {_fmt_ts(r['ts'])}\n"
        )
        if r.get("lesson"):
            lines.append(f"  💡 *{r['lesson'][:120]}...*\n")
        lines.append("")

    return "\n".join(lines)


@mcp.tool(
    name="idim_get_performance",
    annotations={
        "title": "Get Idim Ikang Performance Stats",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def idim_get_performance(params: PerformanceInput) -> str:
    """Get aggregated performance statistics for Idim Ikang v1.5.

    Returns win rate, profit factor, average R-multiple, drawdown,
    and per-regime breakdown for all resolved trades.

    Args:
        params (PerformanceInput):
            - source_filter (str): 'observer_live' for v1.5 only, 'all' for all signals

    Returns:
        str: Markdown performance report with overall and per-regime stats
    """
    source_clause = "AND source = 'observer_live'" if params.source_filter != "all" else ""

    sql = f"""
        SELECT
            outcome,
            regime,
            COUNT(*) as cnt,
            AVG(r_multiple) as avg_r,
            SUM(CASE WHEN r_multiple > 0 THEN r_multiple ELSE 0 END) as gross_win,
            SUM(CASE WHEN r_multiple < 0 THEN ABS(r_multiple) ELSE 0 END) as gross_loss
        FROM signals
        WHERE outcome IN ('WIN','PARTIAL_WIN','LOSS') {source_clause}
        GROUP BY outcome, regime
        ORDER BY regime, outcome
    """

    overall_sql = f"""
        SELECT
            COUNT(*) FILTER (WHERE outcome IN ('WIN','PARTIAL_WIN')) as wins,
            COUNT(*) FILTER (WHERE outcome = 'LOSS') as losses,
            COUNT(*) FILTER (WHERE outcome IS NULL OR outcome = 'PERSISTING') as open_trades,
            AVG(r_multiple) FILTER (WHERE outcome IN ('WIN','PARTIAL_WIN','LOSS')) as avg_r,
            SUM(r_multiple) FILTER (WHERE r_multiple > 0) as gross_win,
            SUM(ABS(r_multiple)) FILTER (WHERE r_multiple < 0) as gross_loss,
            MIN(r_multiple) as max_loss,
            MAX(r_multiple) as max_win
        FROM signals
        WHERE 1=1 {source_clause}
    """

    try:
        overall = _query(overall_sql)
        breakdown = _query(sql)
    except Exception as e:
        return f"Error computing performance: {e}"

    o = overall[0] if overall else {}
    wins = o.get("wins") or 0
    losses = o.get("losses") or 0
    total_closed = wins + losses
    wr = (wins / total_closed * 100) if total_closed > 0 else 0
    gw = float(o.get("gross_win") or 0)
    gl = float(o.get("gross_loss") or 0)
    pf = (gw / gl) if gl > 0 else float("inf")
    avg_r = float(o.get("avg_r") or 0)

    lines = [
        f"## Idim Ikang Performance ({SERVER_VERSION})",
        f"Source: `{params.source_filter}`\n",
        "### Overall",
        f"- **Closed trades**: {total_closed} ({wins}W / {losses}L)",
        f"- **Open**: {o.get('open_trades') or 0}",
        f"- **Win Rate**: {wr:.1f}%",
        f"- **Profit Factor**: {pf:.2f}" if pf != float("inf") else "- **Profit Factor**: ∞ (no losses)",
        f"- **Avg R**: {avg_r:+.2f}R",
        f"- **Best trade**: {float(o.get('max_win') or 0):+.1f}R",
        f"- **Worst trade**: {float(o.get('max_loss') or 0):+.1f}R",
        "",
        "### Per-Regime Breakdown",
    ]

    regimes: Dict[str, Dict] = {}
    for row in breakdown:
        reg = row["regime"] or "UNKNOWN"
        if reg not in regimes:
            regimes[reg] = {"wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0}
        if row["outcome"] in ("WIN", "PARTIAL_WIN"):
            regimes[reg]["wins"] += row["cnt"]
            regimes[reg]["gross_win"] += float(row["gross_win"] or 0)
        elif row["outcome"] == "LOSS":
            regimes[reg]["losses"] += row["cnt"]
            regimes[reg]["gross_loss"] += float(row["gross_loss"] or 0)

    for reg, d in sorted(regimes.items()):
        tc = d["wins"] + d["losses"]
        rwr = (d["wins"] / tc * 100) if tc > 0 else 0
        rpf = (d["gross_win"] / d["gross_loss"]) if d["gross_loss"] > 0 else float("inf")
        rpf_str = f"{rpf:.2f}" if rpf != float("inf") else "∞"
        lines.append(f"- **{reg}**: {tc} trades | WR {rwr:.0f}% | PF {rpf_str}")

    return "\n".join(lines)


@mcp.tool(
    name="idim_get_gate_status",
    annotations={
        "title": "Get Current Gate Rejection Summary",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def idim_get_gate_status(params: GateStatusInput) -> str:
    """Get current gate rejection breakdown from live scanner logs.

    Shows which gates are blocking signals most frequently in recent cycles,
    including BTC regime gate, squeeze gate, directional gates, and score gates.

    Args:
        params (GateStatusInput):
            - tail_lines (int): How many log lines to analyze (default 200)

    Returns:
        str: Markdown summary of gate rejections and current market state
    """
    log_path = os.path.expanduser(
        "~/MoStar/IdimIkang-main/observer_bundle/logs/scanner.log"
    )

    if not os.path.exists(log_path):
        return "Scanner log not found. Is the scanner running?"

    try:
        with open(log_path, "r") as f:
            all_lines = f.readlines()
        lines = all_lines[-params.tail_lines:]
    except Exception as e:
        return f"Error reading scanner log: {e}"

    gate_counts: Dict[str, int] = {}
    cycle_count = 0
    pairs_processed_count = 0
    signals_emitted_count = 0
    btc_regime = "UNKNOWN"

    for line in lines:
        if "rejected at G" in line:
            try:
                gate_part = line.split("rejected at ")[1].strip()
                gate_key = gate_part.split("(")[0].strip()
                gate_counts[gate_key] = gate_counts.get(gate_key, 0) + 1
            except IndexError:
                pass
        if "CYCLE COMPLETE" in line:
            cycle_count += 1
            try:
                if "pairs_processed=" in line:
                    processed = int(line.split("pairs_processed=")[1].split("|")[0])
                    pairs_processed_count += processed
                elif "candidates=" in line:
                    # Legacy fallback for older log lines
                    processed = int(line.split("candidates=")[1].split("|")[0])
                    pairs_processed_count += processed
            except (IndexError, ValueError):
                pass
            try:
                if "signals_emitted=" in line:
                    emitted = int(line.split("signals_emitted=")[1].split("|")[0])
                    signals_emitted_count += emitted
                elif "fired=" in line:
                    emitted = int(line.split("fired=")[1].split("|")[0])
                    signals_emitted_count += emitted
            except (IndexError, ValueError):
                pass
        if "btc_regime=" in line:
            try:
                btc_regime = line.split("btc_regime=")[1].split()[0].rstrip(",}")
            except IndexError:
                pass

    sorted_gates = sorted(gate_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    output = [
        "## Idim Ikang Gate Status",
        f"Analyzed last {params.tail_lines} log lines\n",
        f"- **Cycles scanned**: {cycle_count}",
        f"- **Total pairs processed**: {pairs_processed_count}",
        f"- **Avg pairs processed/cycle**: {pairs_processed_count/cycle_count:.1f}" if cycle_count else "- **Avg pairs processed/cycle**: —",
        f"- **Signals emitted**: {signals_emitted_count}",
        f"- **Avg signals/cycle**: {signals_emitted_count/cycle_count:.1f}" if cycle_count else "- **Avg signals/cycle**: —",
        f"- **BTC Regime (latest)**: `{btc_regime}`",
        "",
        "### Top Gate Rejections",
    ]

    for gate, count in sorted_gates:
        output.append(f"- **{gate}**: {count} rejections")

    if not sorted_gates:
        output.append("No rejections found — scanner may be idle.")

    return "\n".join(output)


@mcp.tool(
    name="idim_get_lessons",
    annotations={
        "title": "Get DCX0 Trade Lessons",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def idim_get_lessons(params: LessonsInput) -> str:
    """Retrieve trade lessons generated by DCX0 (phi4) for resolved trades.

    Each lesson is the sovereign intelligence's analysis of what happened
    in the trade and what the system should learn from it.

    Args:
        params (LessonsInput):
            - limit (int): Number of lessons to return (default 5)

    Returns:
        str: Markdown-formatted lessons from resolved trades
    """
    sql = """
        SELECT pair, side, score, regime, outcome, r_multiple, lesson, updated_at
        FROM signals
        WHERE lesson IS NOT NULL AND outcome IN ('WIN','PARTIAL_WIN','LOSS')
        ORDER BY updated_at DESC
        LIMIT %s
    """
    try:
        rows = _query(sql, (params.limit,))
    except Exception as e:
        return f"Error querying lessons: {e}"

    if not rows:
        return (
            "No trade lessons yet. Lessons are generated by DCX0 (phi4) after trades resolve.\n"
            "Run `trade_learner.py` to generate lessons for existing closed trades."
        )

    outcome_emoji = {
        "WIN": "✅", "PARTIAL_WIN": "🟡", "LOSS": "❌"
    }

    lines = ["## Idim Ikang — DCX0 Trade Lessons\n"]
    for r in rows:
        emoji = outcome_emoji.get(r.get("outcome"), "❓")
        r_str = f"{r['r_multiple']:+.1f}R" if r.get("r_multiple") is not None else "—"
        lines += [
            f"### {emoji} {r['pair']} {r['side']} | {r['outcome']} {r_str}",
            f"*Score: {r['score']} | Regime: {r['regime']} | {_fmt_ts(r['updated_at'])}*\n",
            f"{r['lesson']}\n",
            "---",
        ]

    return "\n".join(lines)


@mcp.tool(
    name="idim_get_open_trades",
    annotations={
        "title": "Get Currently Open Trades",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def idim_get_open_trades(_: None = None) -> str:
    """Get all currently open/persisting signals being tracked by the outcome tracker.

    Shows live positions with entry, stop loss, take profit levels,
    and adverse excursion (how far price moved against the position).

    Returns:
        str: Markdown summary of all open positions
    """
    sql = """
        SELECT pair, side, score, regime, entry, stop_loss, take_profit,
               adverse_excursion, ts, created_at
        FROM signals
        WHERE outcome IS NULL OR outcome = 'PERSISTING'
        ORDER BY created_at DESC
    """
    try:
        rows = _query(sql)
    except Exception as e:
        return f"Error querying open trades: {e}"

    if not rows:
        return "No open trades currently. System is watching for setups. 🜂"

    lines = [f"## Open Positions ({len(rows)} active)\n"]
    for r in rows:
        ae = r.get("adverse_excursion")
        ae_str = f"{float(ae):.4f}" if ae is not None else "—"
        lines += [
            f"**{r['pair']}** {r['side']} | Score: {r['score']} | Regime: {r['regime']}",
            f"  Entry: {r['entry']} | SL: {r['stop_loss']:.4f} | TP: {r['take_profit']:.4f}",
            f"  Adverse excursion: {ae_str} | Opened: {_fmt_ts(r['ts'])}",
            "",
        ]

    return "\n".join(lines)


# ─── Entry ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
