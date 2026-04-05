#!/usr/bin/env python3
import sys
import os
from datetime import datetime, timezone

# Add parent dir to sys.path if needed
sys.path.append(os.getcwd())

import scanner

def test_96_formatting():
    print("--- Testing Telegram API 9.6 Institutional Alerting ---")
    
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
        "ts": datetime.now(timezone.utc),
        "vwap_delta": 0.015,
        "reason_trace": {
            "recent_squeeze_fire": True,
            "volume_ratio": 1.45,
            "derivatives_bonus": 30
        }
    }
    
    html, markup = scanner.format_sovereign_alert(mock_sig)
    
    print("\n[HTML PAYLOAD]")
    print(html)
    
    print("\n[MARKUP DICTIONARY]")
    import json
    print(json.dumps(markup, indent=2))
    
    # 9.6 Feature Verification
    has_style = any(
        "style" in btn for row in markup["inline_keyboard"] for btn in row
    )
    print(f"\nAPI 9.6 Styles Detected: {'✅ YES' if has_style else '❌ NO'}")
    
    success_style = markup["inline_keyboard"][0][0].get("style")
    print(f"Primary Button Style: {success_style} (Expected: success)")
    
    if success_style == "success" and has_style:
        print("\n[VERIFICATION] Logic matches Bot API 9.6 documentation.")
    else:
        print("\n[ERROR] Missing style attributes.")
        sys.exit(1)

if __name__ == "__main__":
    test_96_formatting()
