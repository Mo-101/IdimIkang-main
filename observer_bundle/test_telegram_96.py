#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.getcwd())

import scanner


def _contains_style(value):
    if isinstance(value, dict):
        if 'style' in value:
            return True
        return any(_contains_style(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_style(child) for child in value)
    return False


def test_telegram_markup():
    print("--- Testing Telegram alert compatibility ---")

    mock_sig = {
        "signal_id": "test-uuid-96",
        "pair": "SOLUSDT",
        "side": "LONG",
        "entry": 145.50,
        "stop_loss": 142.10,
        "tp1": 148.00,
        "tp2": 155.00,
        "score": 85,
        "regime": "STRONG_UPTREND",
        "logic_version": "v1.5-quant-alpha",
        "config_version": "v1.5-quant-alpha",
        "ts": datetime.now(timezone.utc),
        "vwap_delta": 0.015,
        "reason_trace": {
            "recent_squeeze_fire": True,
            "volume_ratio": 1.45,
            "derivatives_bonus": 30,
        },
        "signal_family": "trend",
    }

    html_payload, markup = scanner.format_sovereign_alert(mock_sig)

    print("\n[HTML PAYLOAD]")
    print(html_payload)

    print("\n[MARKUP DICTIONARY]")
    print(json.dumps(markup, indent=2))

    if _contains_style(markup):
        print("\n[ERROR] Unsupported Telegram button style fields are still present.")
        sys.exit(1)

    if "inline_keyboard" not in markup or not markup["inline_keyboard"]:
        print("\n[ERROR] Missing inline keyboard.")
        sys.exit(1)

    print("\n[VERIFICATION] Markup is Telegram-compatible and free of unsupported style fields.")


if __name__ == "__main__":
    test_telegram_markup()
