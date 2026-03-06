"""Telegram bot — full trading assistant via Telegram chat."""
import os
import json
import logging
import requests
import time
from google.genai import types
from dotenv import load_dotenv
from gemini import llm_client, MODEL, extract_text
from tools import CONFIRM_REQUIRED, execute_function, make_gemini_config

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

BOT_TOKEN = os.getenv("telegram_bot_token", "")
ALLOWED_CHAT_ID = os.getenv("telegram_chat_id", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram_bot")

gemini_config = make_gemini_config(
    system_instruction="""You are a trading assistant for the Indian stock market (NSE) via DhanHQ broker, communicating over Telegram.
Rules:
- Keep responses concise (Telegram messages have limits).
- Use search_stocks to find symbols when user mentions company names.
- For trade actions, clearly state what you'll do. The user must reply YES to confirm.
- For read-only operations, execute immediately.
- Format financial data with Rs. symbol.
- Use get_quote for current stock/index prices and technical analysis.
- Use get_market_overview for overall market status.
- Use web_search for market news, analysis, or real-time data.
- Default to CNC product type unless user says intraday."""
)

# --- Telegram API helpers ---

def tg_api(method, **kwargs):
    resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=kwargs, timeout=30)
    return resp.json()


def send_message(chat_id, text):
    for i in range(0, len(text), 4000):
        tg_api("sendMessage", chat_id=chat_id, text=text[i:i+4000])


def send_typing(chat_id):
    tg_api("sendChatAction", chat_id=chat_id, action="typing")


# --- Chat session management ---

sessions = {}  # chat_id -> {"contents": [...], "pending": None}


def get_session(chat_id):
    if chat_id not in sessions:
        sessions[chat_id] = {
            "contents": [
                types.Content(role="user", parts=[types.Part(text="You are my trading assistant.")]),
                types.Content(role="model", parts=[types.Part(text="I'm your DhanHQ trading assistant on Telegram. How can I help?")]),
            ],
            "pending": None,
        }
    return sessions[chat_id]


def process_gemini_response(response, session):
    """Process Gemini response, handle function calls. Returns (text, pending_confirmation)."""
    contents = session["contents"]

    for _ in range(10):
        if not response.candidates or not response.candidates[0].content.parts:
            break

        function_calls = [p for p in response.candidates[0].content.parts if p.function_call]
        if not function_calls:
            break

        contents.append(response.candidates[0].content)
        function_response_parts = []

        for part in function_calls:
            fc = part.function_call
            func_name = fc.name
            args = dict(fc.args)

            if func_name in CONFIRM_REQUIRED:
                session["pending"] = {
                    "func_name": func_name,
                    "args": args,
                    "gemini_content": response.candidates[0].content,
                }
                contents.pop()
                desc = f"{func_name}: {json.dumps(args, indent=2)}"
                return f"Confirm this action?\n\n{desc}\n\nReply YES to execute or NO to cancel.", True

            result = execute_function(func_name, args)
            function_response_parts.append(
                types.Part.from_function_response(name=func_name, response=result)
            )

        if function_response_parts:
            contents.append(types.Content(role="user", parts=function_response_parts))
            response = llm_client.models.generate_content(model=MODEL, contents=contents, config=gemini_config)

    # Extract final text
    text = ""
    if response.candidates and response.candidates[0].content.parts:
        contents.append(response.candidates[0].content)
        text = extract_text(response)

    return text or "(no response)", False


def download_voice(file_id):
    """Download a voice/audio file from Telegram, return bytes."""
    resp = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile", params={"file_id": file_id}, timeout=10)
    data = resp.json()
    if not data.get("ok"):
        return None
    file_path = data["result"]["file_path"]
    audio = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}", timeout=30)
    return audio.content if audio.status_code == 200 else None


def handle_voice(chat_id, file_id):
    """Handle a voice message — send audio to Gemini for understanding + function calling."""
    audio_bytes = download_voice(file_id)
    if not audio_bytes:
        return "Sorry, couldn't download the voice message."

    session = get_session(chat_id)
    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg")
    session["contents"].append(types.Content(role="user", parts=[audio_part]))

    try:
        response = llm_client.models.generate_content(
            model=MODEL, contents=session["contents"], config=gemini_config
        )
        reply, _ = process_gemini_response(response, session)
        return reply
    except Exception as e:
        session["contents"].pop()
        return f"Error processing voice: {e}"


def handle_message(chat_id, text):
    """Handle an incoming Telegram message."""
    session = get_session(chat_id)

    if text.strip().lower() in ("/clear", "/reset"):
        sessions.pop(chat_id, None)
        return "Chat cleared. How can I help?"

    if session["pending"]:
        pc = session["pending"]
        upper = text.strip().upper()
        if upper in ("YES", "Y"):
            session["pending"] = None
            result = execute_function(pc["func_name"], pc["args"])
            session["contents"].append(pc["gemini_content"])
            session["contents"].append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=pc["func_name"], response=result)
            ]))
            response = llm_client.models.generate_content(
                model=MODEL, contents=session["contents"], config=gemini_config
            )
            reply, _ = process_gemini_response(response, session)
            return reply
        else:
            session["pending"] = None
            return "Action cancelled."

    session["contents"].append(types.Content(role="user", parts=[types.Part(text=text)]))
    try:
        response = llm_client.models.generate_content(
            model=MODEL, contents=session["contents"], config=gemini_config
        )
        reply, _ = process_gemini_response(response, session)
        return reply
    except Exception as e:
        session["contents"].pop()
        return f"Error: {e}"


# --- Long polling loop ---

def main():
    if not BOT_TOKEN:
        print("ERROR: telegram_bot_token not set in .env")
        return

    # Start alert checker in background (checks every 5 minutes)
    from alerts import start_alert_thread
    start_alert_thread(interval_minutes=5)

    log.info("Telegram bot starting...")
    me = tg_api("getMe")
    if me.get("ok"):
        log.info(f"Bot: @{me['result']['username']}")
    else:
        log.error(f"Failed to connect: {me}")
        return

    offset = 0
    while True:
        try:
            updates = tg_api("getUpdates", offset=offset, timeout=30)
            if not updates.get("ok"):
                time.sleep(5)
                continue

            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message")
                if not msg:
                    continue

                chat_id = str(msg["chat"]["id"])

                if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
                    send_message(chat_id, "Unauthorized. Set your chat_id in .env.")
                    log.warning(f"Unauthorized access from chat_id: {chat_id}")
                    continue

                send_typing(chat_id)

                # Voice/audio messages
                voice = msg.get("voice") or msg.get("audio")
                if voice:
                    log.info(f"Voice from {chat_id} ({voice.get('duration', '?')}s)")
                    reply = handle_voice(chat_id, voice["file_id"])
                    send_message(chat_id, reply)
                    continue

                # Text messages
                text = msg.get("text")
                if not text:
                    continue

                log.info(f"Message from {chat_id}: {text[:100]}")
                reply = handle_message(chat_id, text)
                send_message(chat_id, reply)

        except KeyboardInterrupt:
            log.info("Bot stopped.")
            break
        except Exception as e:
            log.error(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
