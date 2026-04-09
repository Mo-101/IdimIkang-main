#!/usr/bin/env python3
import logging
import os

from dotenv import load_dotenv

from telegram_alerts import send_telegram_sync

load_dotenv()

LOGGER = logging.getLogger(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def send_test_alert() -> None:
    if not TOKEN or not CHAT_ID:
        print(f"FAILED: Missing credentials. TOKEN={bool(TOKEN)}, CHAT_ID={bool(CHAT_ID)}")
        return

    text = (
        "<b>SOVEREIGN HANDSHAKE</b>\n\n"
        "<b>STATUS:</b> <code>NODE_ACTIVE</code>\n"
        "<b>ENGINE:</b> Idim Ikang\n"
        "<b>ALERT PATH:</b> <code>TELEGRAM_READY</code>\n\n"
        "<i>Handshake probe from the observer bundle.</i>"
    )
    markup = {
        "inline_keyboard": [[
            {"text": "VERIFY NODE", "callback_data": "verify_node"}
        ]]
    }

    print(f"Sending to configured chat id: {CHAT_ID}...")
    ok = send_telegram_sync(
        text,
        reply_markup=markup,
        bot_token=TOKEN,
        chat_id=CHAT_ID,
        context="handshake",
        logger=LOGGER,
    )
    if ok:
        print("SUCCESS: Handshake sent to Telegram.")
    else:
        print("FAILED: Telegram rejected or could not deliver the handshake.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    send_test_alert()
