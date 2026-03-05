"""Telegram notification helper. Used by sip.py and can be used standalone."""
import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

BOT_TOKEN = os.getenv("telegram_bot_token", "")
CHAT_ID = os.getenv("telegram_chat_id", "")


def send_telegram(message, parse_mode="Markdown"):
    """Send a message via Telegram Bot API."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": parse_mode},
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception:
        return False
