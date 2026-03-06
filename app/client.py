import os
import json
import logging
import time
import jwt
import requests
import pyotp
from dhanhq import dhanhq
from dotenv import load_dotenv, set_key

ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(ENV_PATH)

log = logging.getLogger("client")

DHAN_CLIENT_ID = os.getenv("client_id")
DHAN_NUMERIC_ID = os.getenv("dhan_client_id", "")  # numeric ID for auth API
TOTP_SECRET = os.getenv("dhan_totp_secret", "")
TRADING_PIN = os.getenv("dhan_trading_pin", "")


def _is_token_valid(token):
    """Check if JWT token expires more than 2 hours from now."""
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp", 0)
        return exp - time.time() > 7200  # valid for > 2 hours
    except Exception:
        return False


def _get_numeric_client_id():
    """Get numeric dhanClientId — from env or by decoding existing JWT."""
    if DHAN_NUMERIC_ID:
        return DHAN_NUMERIC_ID
    try:
        token = os.getenv("access_token", "")
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload.get("dhanClientId", "")
    except Exception:
        return ""


def _generate_token():
    """Generate a fresh access token using TOTP + PIN via Dhan auth API."""
    if not TOTP_SECRET or not TRADING_PIN:
        return None

    client_id = _get_numeric_client_id()
    if not client_id:
        log.error("No numeric dhanClientId available for token generation")
        return None

    totp_code = pyotp.TOTP(TOTP_SECRET).now()
    try:
        resp = requests.post(
            "https://auth.dhan.co/app/generateAccessToken",
            params={
                "dhanClientId": client_id,
                "pin": TRADING_PIN,
                "totp": totp_code,
            },
            timeout=15,
        )
        data = resp.json()
        token = data.get("accessToken") or data.get("access_token")
        if token:
            log.info("Generated fresh Dhan access token via TOTP")
            # Persist to .env so other processes (sip.py, telegram_bot.py) pick it up
            set_key(ENV_PATH, "access_token", token)
            return token
        else:
            log.error(f"Token generation failed: {data}")
    except Exception as e:
        log.error(f"Token generation error: {e}")
    return None


def get_access_token():
    """Get a valid access token — refresh via TOTP if expired."""
    token = os.getenv("access_token", "")

    if _is_token_valid(token):
        return token

    log.info("Access token expired or expiring soon, refreshing...")
    new_token = _generate_token()
    if new_token:
        return new_token

    log.warning("Could not refresh token, using existing (may be expired)")
    return token


access_token = get_access_token()
dhan = dhanhq(DHAN_CLIENT_ID, access_token)
