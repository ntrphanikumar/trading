import os
import json
import logging
from datetime import date
from google import genai
from google.genai import types
from dotenv import load_dotenv
from orders import place_market_order
from portfolio import get_holdings, get_fund_limits

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Configure logging
logging.basicConfig(
    filename="sip.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("sip")

# Daily SIP budget
DAILY_BUDGET = int(os.getenv("daily_sip_budget", 2000))

# SIP-eligible ETFs
SIP_ETFS = ["NIFTYBEES", "MID150BEES", "HDFCSML250", "GOLDCASE", "SILVERBEES"]

# Budget carry-forward tracker
BUDGET_FILE = os.path.join(os.path.dirname(__file__), "sip_budget.json")

# Trade history
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "sip_history.json")


def is_market_open():
    """Ask LLM with Google Search grounding if NSE is open today."""
    try:
        resp = llm_client.models.generate_content(
            model=MODEL,
            contents="Is the Indian stock market (NSE) open for trading today? Reply with only YES or NO.",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = ""
        for part in resp.candidates[0].content.parts:
            if not getattr(part, "thought", False) and part.text:
                text += part.text
        return "YES" in text.upper().strip()
    except Exception as e:
        log.warning(f"Could not check market status: {e}")
    return True  # Default: assume open


def load_carry_forward():
    """Load carry-forward amount from previous holiday accumulations."""
    if os.path.exists(BUDGET_FILE):
        with open(BUDGET_FILE) as f:
            return json.load(f).get("carry_forward", 0)
    return 0


def save_carry_forward(amount):
    """Save carry-forward budget."""
    with open(BUDGET_FILE, "w") as f:
        json.dump({"carry_forward": round(amount, 2)}, f)


def save_trade_history(date_str, budget, reasoning, orders, results):
    """Append today's SIP run to trade history."""
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history = json.load(f)

    history.append({
        "date": date_str,
        "budget": budget,
        "reasoning": reasoning,
        "orders": orders,
        "results": results,
    })

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

# Vertex AI setup
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
    os.path.dirname(__file__), os.getenv("google_service_account")
)
llm_client = genai.Client(
    vertexai=True,
    project=os.getenv("google_project_id"),
    location=os.getenv("google_location", "global"),
)
MODEL = "gemini-3.1-flash-preview"


def get_portfolio_snapshot():
    """Fetch current holdings for SIP ETFs."""
    holdings = get_holdings()
    if holdings.get("status") != "success" or not holdings.get("data"):
        return None

    snapshot = {}
    for h in holdings["data"]:
        sym = h.get("tradingSymbol", "")
        if sym in SIP_ETFS:
            qty = int(h.get("totalQty", 0))
            avg = float(h.get("avgCostPrice", 0))
            ltp = float(h.get("lastTradedPrice", 0))
            value = qty * ltp
            pnl_pct = ((ltp - avg) / avg * 100) if avg > 0 else 0
            snapshot[sym] = {
                "qty": qty,
                "avg_price": round(avg, 2),
                "ltp": round(ltp, 2),
                "value": round(value, 2),
                "pnl_pct": round(pnl_pct, 2),
            }
    return snapshot


def ask_llm_for_allocation(snapshot, budget):
    """Ask Gemini to decide today's SIP allocation based on portfolio + market conditions."""
    total_value = sum(v["value"] for v in snapshot.values())

    portfolio_summary = json.dumps({
        "budget": budget,
        "total_sip_portfolio_value": round(total_value, 2),
        "holdings": {
            sym: {
                **info,
                "allocation_pct": round(info["value"] / total_value * 100, 1) if total_value > 0 else 0,
            }
            for sym, info in snapshot.items()
        },
    }, indent=2)

    prompt = f"""You are a portfolio rebalancing advisor for an Indian retail investor running a daily SIP.

Here is the current portfolio of ETFs and today's budget:
{portfolio_summary}

ETF descriptions:
- NIFTYBEES: Tracks Nifty 50 (large cap Indian equities)
- MID150BEES: Tracks Nifty Midcap 150 (mid cap Indian equities)
- HDFCSML250: Tracks Nifty Smallcap 250 (small cap Indian equities)
- GOLDCASE: Gold ETF fund of funds
- SILVERBEES: Silver ETF

Use Google Search to check today's market data — index levels, daily changes, sector performance, gold/silver prices, and macro news. Then decide how to allocate Rs.{budget} across these ETFs today.

Strategy — BUY THE DIP, REBALANCE SMART:
1. If an index/asset is DOWN today, allocate MORE to that ETF — it's a better entry point
   e.g. if Nifty Midcap 150 is down 1.5% today, buy more MID150BEES
2. If an ETF is underweight in the portfolio vs ideal allocation, prioritize it
3. If gold/silver is dipping while equities rally, shift more to commodities (or vice versa)
4. Consider the investor's P&L — ETFs with negative P&L may represent averaging-down opportunities
5. Factor in macro conditions — if markets are overheated, favor gold/silver as a hedge
6. Don't blindly spread equally — concentrate on the best opportunity today

You MUST respond with ONLY a valid JSON object in this exact format, nothing else:
{{
  "reasoning": "Brief explanation of your allocation logic",
  "orders": [
    {{"stock_name": "SYMBOL", "quantity": N, "rationale": "why this ETF today"}}
  ]
}}

Rules:
- Only include ETFs where quantity > 0
- Quantities must be whole numbers (you're buying actual units, not fractional)
- Total cost (quantity * ltp) should be close to Rs.{budget} — you have 10% flexibility (up to Rs.{int(budget * 1.1)}) to fit whole units
- Maximize budget utilization — don't leave too much unspent
- You can skip ETFs that are overweight or where market conditions don't favor buying
- Use the LTP values from the portfolio data for cost calculations"""

    response = llm_client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MEDIUM,
                include_thoughts=True,
            ),
            temperature=0.3,
        ),
    )

    # Extract text from response (skip thought parts)
    text = ""
    for part in response.candidates[0].content.parts:
        if not part.thought and part.text:
            text += part.text

    # Parse JSON from response (handle markdown code blocks)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]  # remove ```json line
        text = text.rsplit("```", 1)[0]  # remove trailing ```

    return json.loads(text)


def run_sip():
    log.info("=" * 40)

    # Check if market is open
    if not is_market_open():
        carry = load_carry_forward() + DAILY_BUDGET
        save_carry_forward(carry)
        log.info(f"Market closed/holiday — carried forward Rs.{DAILY_BUDGET}, total carry Rs.{carry}")
        print(f"Market is closed today. Rs.{DAILY_BUDGET} carried forward (total: Rs.{carry})")
        return

    carry = load_carry_forward()
    budget = DAILY_BUDGET + carry
    log.info(f"SIP run started — daily Rs.{DAILY_BUDGET}, carry Rs.{carry}, effective Rs.{budget}")

    # Check funds
    funds = get_fund_limits()
    if funds.get("status") != "success":
        log.error(f"Failed to fetch fund limits: {funds}")
        print(f"ERROR: Could not fetch fund limits: {funds}")
        return

    available = float(funds.get("data", {}).get("availabelBalance", 0))
    log.info(f"Available balance: Rs.{available}")

    if available < budget:
        log.warning(f"Insufficient balance Rs.{available} < Rs.{budget}")
        print(f"Insufficient balance Rs.{available:.0f} (need Rs.{budget}), skipping SIP")
        return

    # Get portfolio snapshot
    snapshot = get_portfolio_snapshot()
    if snapshot is None:
        print("ERROR: Could not fetch holdings")
        return

    total_value = sum(v["value"] for v in snapshot.values())
    print(f"\nSIP Portfolio: Rs.{total_value:,.0f}")
    print(f"Budget: Rs.{DAILY_BUDGET}/day" + (f" + Rs.{carry:.0f} carried forward = Rs.{budget:.0f}" if carry > 0 else ""))
    print(f"\nCurrent holdings:")
    for sym, info in snapshot.items():
        alloc = info["value"] / total_value * 100 if total_value > 0 else 0
        print(f"  {sym:12s}  qty={info['qty']:>5}  ltp=Rs.{info['ltp']:>8.2f}  "
              f"value=Rs.{info['value']:>10,.0f}  ({alloc:4.1f}%)  P&L={info['pnl_pct']:+.1f}%")

    # Ask LLM for today's allocation
    print(f"\nAsking Gemini for today's allocation...")
    try:
        decision = ask_llm_for_allocation(snapshot, budget)
    except Exception as e:
        log.error(f"LLM error: {e}")
        print(f"ERROR: LLM failed — {e}")
        return

    reasoning = decision.get("reasoning", "")
    orders = decision.get("orders", [])

    print(f"\nGemini's reasoning: {reasoning}")
    log.info(f"LLM reasoning: {reasoning}")

    if not orders:
        print("No orders recommended today.")
        save_carry_forward(0)
        return

    # Show and validate orders
    print(f"\nRecommended orders:")
    total_cost = 0
    for o in orders:
        sym = o["stock_name"]
        qty = o["quantity"]
        ltp = snapshot.get(sym, {}).get("ltp", 0)
        cost = qty * ltp
        total_cost += cost
        print(f"  BUY {qty:>4} x {sym:12s} @ Rs.{ltp:>8.2f} = Rs.{cost:>8.0f}  ({o.get('rationale', '')})")
    print(f"  Total: Rs.{total_cost:,.0f}")

    if total_cost > budget * 1.1:  # 10% tolerance for whole unit rounding
        print(f"\nWARNING: Total Rs.{total_cost:.0f} exceeds budget Rs.{budget:.0f}, skipping")
        log.warning(f"LLM exceeded budget: Rs.{total_cost:.0f} > Rs.{budget:.0f}")
        return

    # Place orders
    print()
    results = []
    for o in orders:
        sym = o["stock_name"]
        qty = o["quantity"]
        if sym not in SIP_ETFS:
            print(f"  {sym}: SKIPPED (not in SIP ETFs)")
            continue
        if qty <= 0:
            continue

        result = place_market_order(
            stock_name=sym,
            quantity=qty,
            transaction_type="BUY",
            product_type="CNC",
        )
        status = "OK" if result.get("status") == "success" else "FAIL"
        log.info(f"{sym} x{qty}: {status} — {result}")
        print(f"  {sym} x{qty}: {status}")
        results.append(status)

    succeeded = sum(1 for s in results if s == "OK")
    save_carry_forward(0)  # Reset carry after trading day attempt
    log.info(f"SIP complete: {succeeded}/{len(results)} orders placed")
    print(f"\nSIP complete: {succeeded}/{len(results)} orders placed")

    # Save trade history
    save_trade_history(
        date_str=date.today().isoformat(),
        budget=budget,
        reasoning=reasoning,
        orders=[
            {"stock_name": o["stock_name"], "quantity": o["quantity"],
             "ltp": snapshot.get(o["stock_name"], {}).get("ltp", 0),
             "status": results[i] if i < len(results) else "SKIPPED"}
            for i, o in enumerate(orders)
        ],
        results={"succeeded": succeeded, "total": len(results)},
    )


if __name__ == "__main__":
    run_sip()
