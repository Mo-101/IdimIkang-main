
import os
import requests
import json
import logging
from dotenv import load_dotenv

# Load env from the bundle dir
env_path = "/home/idona/MoStar/IdimIkang-main/observer_bundle/.env"
load_dotenv(env_path)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_test_alert():
    if not TOKEN or not CHAT_ID:
        print(f"FAILED: Missing credentials. TOKEN={bool(TOKEN)}, CHAT_ID={bool(CHAT_ID)}")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    # Construct a Sovereign Handshake
    text = (
        "<b>[ 🜂 SOVEREIGN HANDSHAKE v1.5-quant-alpha ]</b>\n\n"
        "⚡ <b>STATUS:</b> <pre>NODE_ACTIVE</pre>\n"
        "📊 <b>ENGINE:</b> Idim Ikang v1.5-quant-alpha\n"
        "🛡️ <b>IRON GATES:</b> <code>ARMED & WATCHING</code>\n\n"
        "<i>Telepathy protocol established. Scanner is currently parsing top 30 symbols. "
        "Alerts will fire only on high-conviction Sovereign setups.</i>"
    )
    
    # Markup with a verification button
    markup = {
        "inline_keyboard": [[
            {"text": "⚡ VERIFY NODE", "callback_data": "verify_node", "style": "success"}
        ]]
    }
    
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(markup)
    }

    print(f"Sending to {CHAT_ID}...")
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print("SUCCESS: Handshake sent to Telegram.")
        print(f"Response: {r.json()}")
    except Exception as e:
        print(f"FAILED: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Details: {e.response.text}")

if __name__ == "__main__":
    send_test_alert()
