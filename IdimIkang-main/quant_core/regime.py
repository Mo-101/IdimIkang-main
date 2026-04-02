import pandas as pd

def classify_regime(df_4h: pd.DataFrame) -> dict:
    """
    Computed ONLY on 4h timeframe.
    Regimes: STRONG_UPTREND, UPTREND, RANGING, DOWNTREND, STRONG_DOWNTREND
    """
    if len(df_4h) < 200:
        return {"regime": "unknown", "confidence": 0.0, "reason_trace": "Insufficient data"}

    latest = df_4h.iloc[-1]
    ema20 = latest['ema_20']
    ema50 = latest['ema_50']
    ema200 = latest['ema_200']
    rsi = latest['rsi']
    current_price = latest['close']

    if pd.isna(ema20) or pd.isna(ema50) or pd.isna(ema200) or pd.isna(rsi):
        return {"regime": "unknown", "confidence": 0.0, "reason_trace": "NaN values"}

    reasons = []
    scores = {"STRONG_UPTREND": 0, "UPTREND": 0, "RANGING": 0, "DOWNTREND": 0, "STRONG_DOWNTREND": 0}

    if ema20 > ema50 > ema200:
        reasons.append("EMA alignment bullish")
        scores["STRONG_UPTREND"] += 2
        scores["UPTREND"] += 1
    elif ema20 < ema50 < ema200:
        reasons.append("EMA alignment bearish")
        scores["STRONG_DOWNTREND"] += 2
        scores["DOWNTREND"] += 1
    elif ema20 > ema200:
        scores["UPTREND"] += 1
    elif ema20 < ema200:
        scores["DOWNTREND"] += 1
    else:
        scores["RANGING"] += 1

    if current_price > ema20:
        scores["STRONG_UPTREND"] += 1
        scores["UPTREND"] += 1
    elif current_price < ema20:
        scores["STRONG_DOWNTREND"] += 1
        scores["DOWNTREND"] += 1

    if current_price > ema200:
        scores["UPTREND"] += 1
    elif current_price < ema200:
        scores["DOWNTREND"] += 1

    if rsi > 60:
        scores["STRONG_UPTREND"] += 1
        scores["UPTREND"] += 1
    elif rsi < 40:
        scores["STRONG_DOWNTREND"] += 1
        scores["DOWNTREND"] += 1
    elif 45 <= rsi <= 55:
        scores["RANGING"] += 1

    ema_spread = abs(ema20 - ema200) / ema200 * 100
    if ema_spread < 2.0:
        scores["RANGING"] += 2

    max_score = max(scores.values())
    regime = max(scores, key=scores.get)
    total_score = sum(scores.values())
    confidence = max_score / total_score if total_score > 0 else 0.0

    return {
        "regime": regime,
        "confidence": confidence,
        "reason_trace": " | ".join(reasons) + f" | Final: {regime}"
    }
