"""Shared tool definitions, function registry, and helpers for all chat interfaces."""
import os
import json
import subprocess
from datetime import date
from google.genai import types
from gemini import llm_client, MODEL, extract_text
from orders import place_market_order, place_limit_order, get_order_book, get_pending_orders, cancel_order
from portfolio import get_holdings, get_positions, get_fund_limits
from stocks import search_stocks
from market_data import get_quote, get_market_overview
from alerts import add_alert, remove_alert, list_alerts, send_market_update

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "sip_history.json")

CONFIRM_REQUIRED = {"place_market_order", "place_limit_order", "cancel_order"}


def web_search(query):
    """Separate Gemini call with Google Search grounding for real-time info."""
    resp = llm_client.models.generate_content(
        model=MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            system_instruction="You are a financial research assistant. Provide concise, factual answers about markets, stocks, and financial news. Include specific numbers, dates, and sources when available.",
        ),
    )
    return {"result": extract_text(resp)}


def get_sip_history(last_n=None):
    """Get SIP trade history."""
    if not os.path.exists(HISTORY_FILE):
        return {"trades": [], "message": "No SIP history yet"}
    with open(HISTORY_FILE) as f:
        history = json.load(f)
    if last_n:
        history = history[-int(last_n):]
    return {"trades": history, "total": len(history)}


def get_sip_schedule():
    """Get SIP cron schedule and next execution info."""
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
    "get_quote": get_quote,
    "get_market_overview": get_market_overview,
    "add_alert": add_alert,
    "remove_alert": remove_alert,
    "list_alerts": list_alerts,
    "send_market_update": send_market_update,
}

TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        {
            "name": "place_market_order",
            "description": "Place a market order (buy or sell) for a stock by name. Executes immediately at current market price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_name": {"type": "string", "description": "Trading symbol e.g. NIFTYBEES, HDFCBANK, INFY"},
                    "quantity": {"type": "integer", "description": "Number of shares"},
                    "transaction_type": {"type": "string", "enum": ["BUY", "SELL"], "description": "Buy or sell"},
                    "product_type": {"type": "string", "enum": ["CNC", "INTRADAY"], "description": "CNC for delivery, INTRADAY for same-day. Default CNC."},
                },
                "required": ["stock_name", "quantity", "transaction_type"],
            },
        },
        {
            "name": "place_limit_order",
            "description": "Place a limit order (buy or sell) for a stock at a specific price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_name": {"type": "string", "description": "Trading symbol e.g. NIFTYBEES, HDFCBANK, INFY"},
                    "quantity": {"type": "integer", "description": "Number of shares"},
                    "price": {"type": "number", "description": "Limit price per share"},
                    "transaction_type": {"type": "string", "enum": ["BUY", "SELL"], "description": "Buy or sell"},
                    "product_type": {"type": "string", "enum": ["CNC", "INTRADAY"], "description": "CNC for delivery, INTRADAY for same-day. Default CNC."},
                },
                "required": ["stock_name", "quantity", "price", "transaction_type"],
            },
        },
        {"name": "get_order_book", "description": "Get all orders placed today including their status.", "parameters": {"type": "object", "properties": {}}},
        {"name": "get_pending_orders", "description": "Get only pending/open orders that haven't been executed yet.", "parameters": {"type": "object", "properties": {}}},
        {
            "name": "cancel_order",
            "description": "Cancel a pending order by its order ID.",
            "parameters": {"type": "object", "properties": {"order_id": {"type": "string", "description": "The order ID to cancel"}}, "required": ["order_id"]},
        },
        {"name": "get_holdings", "description": "Get all holdings in the demat account (long-term investments).", "parameters": {"type": "object", "properties": {}}},
        {"name": "get_positions", "description": "Get all open intraday positions for today.", "parameters": {"type": "object", "properties": {}}},
        {"name": "get_fund_limits", "description": "Get available fund balance, margin, and account information.", "parameters": {"type": "object", "properties": {}}},
        {
            "name": "search_stocks",
            "description": "Search for stocks by name or company name. Use this when the user mentions a company and you need to find the trading symbol.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Search query — stock symbol or company name"}}, "required": ["query"]},
        },
        {
            "name": "web_search",
            "description": "Search the web for real-time market data, stock news, analysis, index levels, sector performance, or any financial information. Use when user asks about market conditions, news, or anything requiring current data.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "The search query for market/financial information"}}, "required": ["query"]},
        },
        {
            "name": "get_sip_history",
            "description": "Get the history of automated SIP trades — dates, ETFs bought, quantities, budget, reasoning, and success/failure. Use when user asks about past SIP trades, investment history, or how much was invested.",
            "parameters": {"type": "object", "properties": {"last_n": {"type": "integer", "description": "Return only the last N trades. Omit to get all."}}},
        },
        {
            "name": "get_sip_schedule",
            "description": "Get the SIP cron schedule — shows when the next automated SIP will run. Use when user asks about SIP schedule, next run, or cron configuration.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_quote",
            "description": "Get real-time price quote and technical indicators (RSI, MACD, EMAs, Bollinger Bands, etc.) for any stock or index from TradingView. Use this for current prices, technical analysis, or when user asks about any stock/index value. Supports NSE stocks, indices (NIFTY, BANKNIFTY, SENSEX), and ETFs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Trading symbol e.g. NIFTY, BANKNIFTY, SENSEX, HDFCBANK, NIFTYBEES, RELIANCE"},
                    "exchange": {"type": "string", "description": "Exchange: NSE (default) or BSE. Use BSE for SENSEX.", "enum": ["NSE", "BSE"]},
                    "interval": {"type": "string", "description": "Timeframe: 1m, 5m, 15m, 1h, 4h, 1d (default), 1w, 1M", "enum": ["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"]},
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "get_market_overview",
            "description": "Get a snapshot of all major Indian market indices — Nifty 50, Bank Nifty, Sensex, Midcap, Smallcap, and India VIX with current values and change. Use when user asks about overall market status or how markets are doing.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "add_alert",
            "description": "Set a price alert for a stock or index. You'll be notified via Telegram when the price crosses the threshold. Use when user says things like 'alert me when Nifty crosses 25000' or 'notify me if HDFCBANK drops below 1500'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Trading symbol e.g. NIFTY, HDFCBANK, RELIANCE"},
                    "condition": {"type": "string", "enum": ["above", "below"], "description": "'above' to alert when price rises above target, 'below' when it drops below"},
                    "price": {"type": "number", "description": "Target price to trigger the alert"},
                    "exchange": {"type": "string", "enum": ["NSE", "BSE"], "description": "Exchange (default NSE)"},
                },
                "required": ["symbol", "condition", "price"],
            },
        },
        {
            "name": "remove_alert",
            "description": "Remove a price alert by its index number. Use list_alerts first to see indices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "0-based index of the alert to remove"},
                },
                "required": ["index"],
            },
        },
        {
            "name": "list_alerts",
            "description": "List all active price alerts. Use when user asks about their alerts or wants to see what alerts are set.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "send_market_update",
            "description": "Send a market overview + portfolio summary to Telegram right now. Use when user asks for a market update or wants a summary sent to their Telegram.",
            "parameters": {"type": "object", "properties": {}},
        },
    ],
)

SYSTEM_INSTRUCTION = f"""You are a trading assistant for the Indian stock market (NSE) via the DhanHQ broker.
Today's date is {date.today().isoformat()}.
You help the user place orders, check their portfolio, and manage trades.

Rules:
- When the user wants to buy or sell, determine the stock_name, quantity, order type (market/limit), and transaction type.
- If the user mentions a company name instead of a symbol, use search_stocks first to find the correct symbol.
- Always confirm details with the user before placing orders by clearly stating what you're about to do.
- For read-only operations (holdings, positions, funds, orders), execute immediately and present results clearly.
- Format financial data in a readable way with Indian rupee symbol where appropriate.
- If a stock is not found, suggest alternatives using search_stocks.
- Default to CNC (delivery) product type unless the user specifies intraday.
- Use get_quote for current stock/index prices and technical analysis.
- Use get_market_overview for overall market status.
- Use web_search for market news, analysis, or information not available via other tools.
- Use add_alert to set price alerts (e.g. "alert me when Nifty crosses 25000"). Alerts are checked every 5 minutes and notifications sent via Telegram.
- Use list_alerts and remove_alert to manage existing alerts.
- Use send_market_update to send a market + portfolio summary to Telegram on demand."""


def make_gemini_config(system_instruction=None):
    """Create a Gemini config with tool declarations and thinking."""
    return types.GenerateContentConfig(
        tools=[TOOL_DECLARATIONS],
        thinking_config=types.ThinkingConfig(thinking_budget=2048, include_thoughts=True),
        system_instruction=system_instruction or SYSTEM_INSTRUCTION,
    )


def execute_function(func_name, args):
    """Execute a registered function by name, returning a dict result."""
    func = FUNCTIONS.get(func_name)
    if not func:
        return {"status": "error", "message": f"Unknown function: {func_name}"}
    try:
        result = func(**args)
        if not isinstance(result, dict):
            result = {"data": result}
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}
