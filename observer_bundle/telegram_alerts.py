from __future__ import annotations

import html
import logging
import os
import re
import threading
import time
from typing import Any

import requests

MAX_TELEGRAM_MESSAGE_LEN = 4096
_NETWORK_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_KEYS_TO_STRIP = {"style"}


def _strip_unsupported_markup(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_unsupported_markup(child)
            for key, child in value.items()
            if key not in _KEYS_TO_STRIP and child is not None
        }
    if isinstance(value, list):
        return [_strip_unsupported_markup(child) for child in value]
    return value


def _to_plain_text(message: str) -> str:
    text = _HTML_TAG_RE.sub("", message)
    return html.unescape(text).strip()


def _truncate(text: str, suffix: str = "\n\n[truncated]") -> str:
    if len(text) <= MAX_TELEGRAM_MESSAGE_LEN:
        return text
    return text[: MAX_TELEGRAM_MESSAGE_LEN - len(suffix)] + suffix


def _build_variants(message: str, reply_markup: dict | None) -> list[dict[str, Any]]:
    plain_text = _truncate(_to_plain_text(message))
    cleaned_markup = _strip_unsupported_markup(reply_markup) if reply_markup else None
    variants = [{"text": plain_text, "reply_markup": cleaned_markup}]
    if cleaned_markup is not None:
        variants.append({"text": plain_text, "reply_markup": None})
    return variants


def send_telegram_sync(
    message: str,
    reply_markup: dict | None = None,
    *,
    bot_token: str | None = None,
    chat_id: str | None = None,
    context: str = "telegram",
    logger: logging.Logger | None = None,
) -> bool:
    active_logger = logger or logging.getLogger(__name__)
    token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    target_chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID") or "").strip()

    if not token or not target_chat_id:
        active_logger.warning("[%s] Telegram delivery disabled: missing bot token or chat id", context)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    variants = _build_variants(message, reply_markup)

    for variant_index, variant in enumerate(variants, start=1):
        payload = {
            "chat_id": target_chat_id,
            "text": variant["text"],
            "disable_web_page_preview": True,
        }
        if variant["reply_markup"] is not None:
            payload["reply_markup"] = variant["reply_markup"]

        for attempt in range(1, 4):
            try:
                response = requests.post(url, json=payload, timeout=(10, 20))
            except requests.RequestException as exc:
                if attempt < 3:
                    time.sleep(attempt)
                    continue
                active_logger.error("[%s] Telegram request failed after %s attempts: %s", context, attempt, exc)
                break

            try:
                body = response.json()
            except ValueError:
                body = {}

            if response.ok and body.get("ok", True):
                active_logger.info(
                    "[%s] Telegram alert delivered via variant %s attempt %s",
                    context,
                    variant_index,
                    attempt,
                )
                return True

            description = body.get("description") or response.text or response.reason
            if response.status_code in _NETWORK_RETRY_STATUS_CODES:
                retry_after = 0
                if isinstance(body.get("parameters"), dict):
                    retry_after = int(body["parameters"].get("retry_after", 0) or 0)
                if attempt < 3:
                    time.sleep(retry_after or attempt)
                    continue

            lowered = description.lower()
            if 'reply markup' in lowered or 'button' in lowered:
                active_logger.warning(
                    "[%s] Telegram rejected markup variant %s (%s); falling back",
                    context,
                    variant_index,
                    description,
                )
                break

            active_logger.error(
                "[%s] Telegram API rejected alert (status=%s, variant=%s): %s",
                context,
                response.status_code,
                variant_index,
                description,
            )
            break

    active_logger.error("[%s] Telegram delivery failed for all fallback variants", context)
    return False


def send_telegram_async(
    message: str,
    reply_markup: dict | None = None,
    *,
    bot_token: str | None = None,
    chat_id: str | None = None,
    context: str = "telegram",
    logger: logging.Logger | None = None,
) -> None:
    thread = threading.Thread(
        target=send_telegram_sync,
        args=(message, reply_markup),
        kwargs={
            "bot_token": bot_token,
            "chat_id": chat_id,
            "context": context,
            "logger": logger,
        },
        daemon=True,
        name=f"telegram-send-{context}",
    )
    thread.start()
