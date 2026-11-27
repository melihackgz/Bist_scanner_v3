from __future__ import annotations
import os
import requests
import streamlit as st
from logger import get_logger

log = get_logger("notifier")


def _get_secret(key: str) -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, "")


def send_telegram_alert(message: str) -> tuple[bool, str]:
    token = _get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = _get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "Telegram anahtarları (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) tanımlı değil."
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=6,
        )
        resp.raise_for_status()
        return True, "Telegram bildirimi gönderildi."
    except Exception as exc:
        log.error("Telegram gönderim hatası: %s", exc)
        return False, f"Telegram hatası: {exc}"
