import json
from collections import Counter, defaultdict

import pandas as pd

import scanner

REQUIRED_15M = [
    "close",
    "ema20",
    "atr14",
    "adx14",
    "squeeze_on",
    "squeeze_fired",
    "recent_squeeze_fire",
]

OPTIONAL_BUT_IMPORTANT = [
    "rsi14",
    "ema50",
    "vwap",
    "volume",
]


def safe_bool(v):
    try:
        return bool(v)
    except Exception:
        return False


def fmt(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    return v


def main():
    scanner._init_pool()
    scanner.refresh_active_universe()
    universe = list(getattr(scanner, "ACTIVE_UNIVERSE", []) or scanner.PAIRS)

    summary = {
        "universe_size": len(universe),
        "ok_symbols": [],
        "problem_symbols": [],
        "base_long_nonzero": 0,
        "base_short_nonzero": 0,
        "missing_cols": defaultdict(list),
        "all_nan_cols": defaultdict(list),
        "fail_reasons_long": Counter(),
        "fail_reasons_short": Counter(),
        "stale_or_bad_data": [],
    }

    rows = []

    for symbol in universe:
        rec = {
            "symbol": symbol,
            "status": "ok",
            "problems": [],
        }

        try:
            df15_raw = scanner.fetch_klines(symbol, "15m", scanner.LOOKBACK_15M)
            df4_raw = scanner.fetch_klines(symbol, "4h", scanner.LOOKBACK_4H)

            if df15_raw is None or df15_raw.empty:
                rec["status"] = "bad_data"
                rec["problems"].append("empty_15m")
                summary["stale_or_bad_data"].append(symbol)
                rows.append(rec)
                continue

            if df4_raw is None or df4_raw.empty:
                rec["status"] = "bad_data"
                rec["problems"].append("empty_4h")
                summary["stale_or_bad_data"].append(symbol)
                rows.append(rec)
                continue

            df15 = scanner.add_indicators(df15_raw.copy())
            regime = scanner.classify_regime(df4_raw)
            latest = df15.iloc[-1]

            rec["ts_15m"] = str(df15_raw.iloc[-1].get("close_time", ""))
            rec["ts_4h"] = str(df4_raw.iloc[-1].get("close_time", ""))
            rec["regime"] = regime

            for col in REQUIRED_15M:
                if col not in df15.columns:
                    rec["problems"].append(f"missing:{col}")
                    summary["missing_cols"][col].append(symbol)
                elif df15[col].isna().all():
                    rec["problems"].append(f"all_nan:{col}")
                    summary["all_nan_cols"][col].append(symbol)

            for col in OPTIONAL_BUT_IMPORTANT:
                if col in df15.columns and df15[col].isna().all():
                    rec["problems"].append(f"all_nan:{col}")
                    summary["all_nan_cols"][col].append(symbol)

            market_ctx = {"funding_rate": 0, "ls_ratio": 1.0}
            long_score, long_trace = scanner.score_long_signal(latest, regime, market_ctx)
            short_score, short_trace = scanner.score_short_signal(latest, regime, market_ctx)

            rec["adx14"] = fmt(latest.get("adx14"))
            rec["atr14"] = fmt(latest.get("atr14"))
            rec["ema20"] = fmt(latest.get("ema20"))
            rec["close"] = fmt(latest.get("close"))
            rec["squeeze_on"] = safe_bool(latest.get("squeeze_on", False))
            rec["squeeze_fired"] = safe_bool(latest.get("squeeze_fired", False))
            rec["recent_squeeze_fire"] = safe_bool(latest.get("recent_squeeze_fire", False))
            rec["base_long"] = fmt(long_score)
            rec["base_short"] = fmt(short_score)
            rec["long_fail"] = list(long_trace.get("reasons_fail", [])) if isinstance(long_trace, dict) else []
            rec["short_fail"] = list(short_trace.get("reasons_fail", [])) if isinstance(short_trace, dict) else []

            if long_score > 0:
                summary["base_long_nonzero"] += 1
            if short_score > 0:
                summary["base_short_nonzero"] += 1

            for reason in rec["long_fail"]:
                summary["fail_reasons_long"][reason] += 1
            for reason in rec["short_fail"]:
                summary["fail_reasons_short"][reason] += 1

            if rec["problems"]:
                rec["status"] = "problem"
                summary["problem_symbols"].append(symbol)
            else:
                summary["ok_symbols"].append(symbol)

        except Exception as e:
            rec["status"] = "error"
            rec["problems"].append(f"exception:{type(e).__name__}:{e}")
            summary["problem_symbols"].append(symbol)

        rows.append(rec)

    df = pd.DataFrame(rows)
    df.to_csv("/tmp/universe_health.csv", index=False)

    out = {
        "universe_size": summary["universe_size"],
        "ok_count": len(summary["ok_symbols"]),
        "problem_count": len(summary["problem_symbols"]),
        "base_long_nonzero": summary["base_long_nonzero"],
        "base_short_nonzero": summary["base_short_nonzero"],
        "missing_cols": {k: v for k, v in summary["missing_cols"].items()},
        "all_nan_cols": {k: v for k, v in summary["all_nan_cols"].items()},
        "top_long_fail_reasons": summary["fail_reasons_long"].most_common(10),
        "top_short_fail_reasons": summary["fail_reasons_short"].most_common(10),
        "bad_data_symbols": summary["stale_or_bad_data"],
        "csv": "/tmp/universe_health.csv",
    }

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
