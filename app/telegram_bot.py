"""Telegram bot — full trading assistant via Telegram chat."""
import os
import json
import logging
import requests
import time
from datetime import date
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
    os.path.dirname(__file__), os.getenv("google_service_account")
)

llm_client = genai.Client(
    vertexai=True,
    project=os.getenv("google_project_id"),
    location=os.getenv("google_location", "global"),
)

MODEL = "gemini-2.5-flash"
BOT_TOKEN = os.getenv("telegram_bot_token", "")
ALLOWED_CHAT_ID = os.getenv("telegram_chat_id", "")
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "sip_history.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram_bot")

# --- Trading functions (same as cli/web) ---
from orders import place_market_order, place_limit_order, get_order_book, get_pending_orders, cancel_order
from portfolio import get_holdings, get_positions, get_fund_limits
from stocks import search_stocks


def web_search(query):
    resp = llm_client.models.generate_content(
        model=MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            system_instruction="You are a financial research assistant. Provide concise, factual answers about markets, stocks, and financial news.",
        ),
    )
    text = ""
    for part in resp.candidates[0].content.parts:
        if not getattr(part, "thought", False) and part.text:
            text += part.text
    return {"result": text}


def get_sip_history(last_n=None):
    if not os.path.exists(HISTORY_FILE):
        return {"trades": [], "message": "No SIP history yet"}
    with open(HISTORY_FILE) as f:
        history = json.load(f)
    if last_n:
        history = history[-int(last_n):]
    return {"trades": history, "total": len(history)}


def get_sip_schedule():
    import subprocess
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            return {"message": "No crontab configured"}
        sip_lines = [l.strip() for l in result.stdout.splitlines() if "sip.py" in l and not l.startswith("#")]
        if not sip_lines:
            return {"message": "No SIP cron job found"}
        return {"cron_entries": sip_lines, "raw_crontab": result.stdout}
    except Exception as e:
        return {"error": str(e)}


# Trade actions that need confirmation
CONFIRM_REQUIRED = {"place_market_order", "place_limit_order", "cancel_order"}

FUNCTIONS = {
    "place_market_order": place_market_order,
    "place_limit_order": place_limit_order,
    "get_order_book": get_order_book,
    "get_pending_orders": get_pending_orders,
    "cancel_order": cancel_order,
    "get_holdings": get_holdings,
    "get_positions": get_positions,
    "get_fund_limits": get_fund_limits,
    "search_stocks": search_stocks,
    "web_search": web_search,
    "get_sip_history": get_sip_history,
    "get_sip_schedule": get_sip_schedule,
}

tool_declarations = types.Tool(
    function_declarations=[
        {
            "name": "place_market_order",
            "description": "Place a market order (buy or sell) for a stock by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_name": {"type": "string"}, "quantity": {"type": "integer"},
                    "transaction_type": {"type": "string", "enum": ["BUY", "SELL"]},
                    "product_type": {"type": "string", "enum": ["CNC", "INTRADAY"]},
                },
                "required": ["stock_name", "quantity", "transaction_type"],
            },
        },
        {
            "name": "place_limit_order",
            "description": "Place a limit order at a specific price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_name": {"type": "string"}, "quantity": {"type": "integer"},
                    "price": {"type": "number"},
                    "transaction_type": {"type": "string", "enum": ["BUY", "SELL"]},
                    "product_type": {"type": "string", "enum": ["CNC", "INTRADAY"]},
                },
                "required": ["stock_name", "quantity", "price", "transaction_type"],
            },
        },
        {"name": "get_order_book", "description": "Get all orders placed today.", "parameters": {"type": "object", "properties": {}}},
        {"name": "get_pending_orders", "description": "Get pending orders.", "parameters": {"type": "object", "properties": {}}},
        {"name": "cancel_order", "description": "Cancel a pending order.", "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}},
        {"name": "get_holdings", "description": "Get demat holdings.", "parameters": {"type": "object", "properties": {}}},
        {"name": "get_positions", "description": "Get intraday positions.", "parameters": {"type": "object", "properties": {}}},
        {"name": "get_fund_limits", "description": "Get fund balance.", "parameters": {"type": "object", "properties": {}}},
        {"name": "search_stocks", "description": "Search stocks by name/symbol.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "web_search", "description": "Search web for market data/news.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "get_sip_history", "description": "Get SIP trade history.", "parameters": {"type": "object", "properties": {"last_n": {"type": "integer"}}}},
        {"name": "get_sip_schedule", "description": "Get SIP cron schedule.", "parameters": {"type": "object", "properties": {}}},
    ],
)

gemini_config = types.GenerateContentConfig(
    tools=[tool_declarations],
    thinking_config=types.ThinkingConfig(thinking_budget=2048, include_thoughts=True),
    system_instruction=f"""You are a trading assistant for the Indian stock market (NSE) via DhanHQ broker, communicating over Telegram.
Today's date is {date.today().isoformat()}.
Rules:
- Keep responses concise (Telegram messages have limits).
- Use search_stocks to find symbols when user mentions company names.
- For trade actions, clearly state what you'll do. The user must reply YES to confirm.
- For read-only operations, execute immediately.
- Format financial data with Rs. symbol.
- Use web_search for market news, analysis, or real-time data.
- Default to CNC product type unless user says intraday.""",
)

# --- Telegram API helpers ---

def tg_api(method, **kwargs):
    resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=kwargs, timeout=30)
    return resp.json()


def send_message(chat_id, text):
    # Telegram message limit is 4096 chars
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
                # Pause for confirmation
                session["pending"] = {
                    "func_name": func_name,
                    "args": args,
                    "gemini_content": response.candidates[0].content,
                }
                contents.pop()  # Remove since we'll re-add after confirmation
                desc = f"{func_name}: {json.dumps(args, indent=2)}"
                return f"Confirm this action?\n\n{desc}\n\nReply YES to execute or NO to cancel.", True

            func = FUNCTIONS.get(func_name)
            if func:
                try:
                    result = func(**args)
                    if not isinstance(result, dict):
                        result = {"data": result}
                except Exception as e:
                    result = {"status": "error", "message": str(e)}
            else:
                result = {"status": "error", "message": f"Unknown: {func_name}"}

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
        for part in response.candidates[0].content.parts:
            if not getattr(part, "thought", False) and part.text:
                text += part.text

    return text or "(no response)", False


def handle_message(chat_id, text):
    """Handle an incoming Telegram message."""
    session = get_session(chat_id)

    # Handle /clear command
    if text.strip().lower() in ("/clear", "/reset"):
        sessions.pop(chat_id, None)
        return "Chat cleared. How can I help?"

    # Handle confirmation responses
    if session["pending"]:
        pc = session["pending"]
        upper = text.strip().upper()
        if upper in ("YES", "Y"):
            session["pending"] = None
            func = FUNCTIONS.get(pc["func_name"])
            try:
                result = func(**pc["args"])
                if not isinstance(result, dict):
                    result = {"data": result}
            except Exception as e:
                result = {"status": "error", "message": str(e)}

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

    # Normal message
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

    log.info("Telegram bot starting...")
    # Get bot info
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
                if not msg or not msg.get("text"):
                    continue

                chat_id = str(msg["chat"]["id"])

                # Security: only respond to allowed chat
                if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
                    send_message(chat_id, "Unauthorized. Set your chat_id in .env.")
                    log.warning(f"Unauthorized access from chat_id: {chat_id}")
                    continue

                text = msg["text"]
                log.info(f"Message from {chat_id}: {text[:100]}")

                send_typing(chat_id)
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
