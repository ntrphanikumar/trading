import os
import json
from datetime import date
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Vertex AI init with service account
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
    os.path.dirname(__file__), os.getenv("google_service_account")
)

client = genai.Client(
    vertexai=True,
    project=os.getenv("google_project_id"),
    location=os.getenv("google_location", "global"),
)

MODEL = "gemini-2.5-flash"

# Import trading functions
from orders import (
    place_market_order,
    place_limit_order,
    get_order_book,
    get_pending_orders,
    cancel_order,
)
from portfolio import get_holdings, get_positions, get_fund_limits
from stocks import search_stocks

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "sip_history.json")

# Functions that modify state — require confirmation
CONFIRM_REQUIRED = {"place_market_order", "place_limit_order", "cancel_order"}


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


def web_search(query):
    """Use a separate Gemini call with Google Search grounding to get real-time info."""
    response = client.models.generate_content(
        model=MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            system_instruction="You are a financial research assistant. Provide concise, factual answers about markets, stocks, and financial news. Include specific numbers, dates, and sources when available.",
        ),
    )
    text = ""
    for part in response.candidates[0].content.parts:
        if not getattr(part, "thought", False) and part.text:
            text += part.text
    return {"result": text}


# Map function names to callables
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

# Tool declarations — function calling only (Google Search via web_search function)
tool_declarations = types.Tool(
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
        {
            "name": "get_order_book",
            "description": "Get all orders placed today including their status.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_pending_orders",
            "description": "Get only pending/open orders that haven't been executed yet.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "cancel_order",
            "description": "Cancel a pending order by its order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID to cancel"},
                },
                "required": ["order_id"],
            },
        },
        {
            "name": "get_holdings",
            "description": "Get all holdings in the demat account (long-term investments).",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_positions",
            "description": "Get all open intraday positions for today.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_fund_limits",
            "description": "Get available fund balance, margin, and account information.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "search_stocks",
            "description": "Search for stocks by name or company name. Use this when the user mentions a company and you need to find the trading symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query — stock symbol or company name"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "web_search",
            "description": "Search the web for real-time market data, stock news, analysis, index levels, sector performance, or any financial information you don't have. Use this whenever the user asks about market conditions, stock performance, news, or anything requiring current data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query for market/financial information"},
                },
                "required": ["query"],
            },
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
    ],
)

config = types.GenerateContentConfig(
    tools=[tool_declarations],
    thinking_config=types.ThinkingConfig(
        thinking_budget=2048,
        include_thoughts=True,
    ),
    system_instruction=f"""You are a trading assistant for the Indian stock market (NSE) via the DhanHQ broker.
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
- Use the web_search function when the user asks about market news, stock analysis, current prices, or any information requiring real-time data.""",
)

SYSTEM_CONTENTS = [
    types.Content(
        role="user",
        parts=[types.Part(text="You are my trading assistant. Help me trade on DhanHQ.")],
    ),
    types.Content(
        role="model",
        parts=[types.Part(text="I'm your DhanHQ trading assistant. I can help you place orders (market/limit), check holdings, positions, fund balance, search for stocks, and answer market research questions with live data. What would you like to do?")],
    ),
]


def format_confirmation(func_name, args):
    """Format a human-readable confirmation message for trade actions."""
    if func_name == "place_market_order":
        return (
            f"\n  >> {args.get('transaction_type', 'BUY')} {args.get('quantity')} shares of "
            f"{args.get('stock_name')} at MARKET price "
            f"(product: {args.get('product_type', 'CNC')})"
            f"\n  Confirm? (y/n): "
        )
    elif func_name == "place_limit_order":
        return (
            f"\n  >> {args.get('transaction_type', 'BUY')} {args.get('quantity')} shares of "
            f"{args.get('stock_name')} at LIMIT price Rs.{args.get('price')} "
            f"(product: {args.get('product_type', 'CNC')})"
            f"\n  Confirm? (y/n): "
        )
    elif func_name == "cancel_order":
        return f"\n  >> Cancel order {args.get('order_id')}\n  Confirm? (y/n): "
    return f"\n  >> Execute {func_name}({args})\n  Confirm? (y/n): "


def process_function_calls(response, contents):
    """Process function calls from Gemini response, handling confirmation for trade actions."""
    while response.candidates and response.candidates[0].content.parts:
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
                confirm = input(format_confirmation(func_name, args))
                if confirm.lower() != "y":
                    result = {"status": "cancelled", "message": "User declined the action"}
                    function_response_parts.append(
                        types.Part.from_function_response(name=func_name, response=result)
                    )
                    continue

            func = FUNCTIONS.get(func_name)
            if func:
                try:
                    result = func(**args)
                    if not isinstance(result, dict):
                        result = {"data": result}
                except Exception as e:
                    result = {"status": "error", "message": str(e)}
            else:
                result = {"status": "error", "message": f"Unknown function: {func_name}"}

            function_response_parts.append(
                types.Part.from_function_response(name=func_name, response=result)
            )

        contents.append(types.Content(role="user", parts=function_response_parts))
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=config,
        )

    return response


def main():
    contents = list(SYSTEM_CONTENTS)

    print("=" * 50)
    print("  DhanHQ Trading Assistant")
    print(f"  Powered by Gemini ({MODEL})")
    print("  Type 'quit' or 'exit' to stop")
    print("=" * 50)
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        contents.append(
            types.Content(role="user", parts=[types.Part(text=user_input)])
        )

        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=config,
            )

            # Process any function calls (may loop multiple times)
            response = process_function_calls(response, contents)

            # Print the final text response
            if response.candidates and response.candidates[0].content.parts:
                contents.append(response.candidates[0].content)

                for part in response.candidates[0].content.parts:
                    if part.thought:
                        pass  # Skip thought parts in display
                    elif part.text:
                        print(f"\nAssistant: {part.text}\n")
            else:
                print("\nAssistant: (no response)\n")

        except Exception as e:
            print(f"\nError: {e}\n")
            contents.pop()


if __name__ == "__main__":
    main()
