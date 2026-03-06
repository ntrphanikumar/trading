import os
import json
import logging
from datetime import date
from google.genai import types
from orders import place_market_order
from portfolio import get_holdings, get_fund_limits
from notify import send_telegram
from gemini import llm_client, extract_text

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
            model=SIP_MODEL,
            contents="Is the Indian stock market (NSE) open for trading today? Reply with only YES or NO.",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = extract_text(resp)
        return "YES" in text.upper().strip()
    except Exception as e:
        log.warning(f"Could not check market status: {e}")
    return True  # Default: assume open


def _load_budget_data():
    """Load budget JSON file, returning {} on missing/empty/invalid."""
    if os.path.exists(BUDGET_FILE):
        try:
            with open(BUDGET_FILE) as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def load_carry_forward():
    """Load carry-forward amount from previous holiday accumulations."""
    return _load_budget_data().get("carry_forward", 0)


def save_carry_forward(amount):
    """Save carry-forward budget."""
    with open(BUDGET_FILE, "w") as f:
        json.dump({"carry_forward": round(amount, 2)}, f)


def already_ran_today():
    """Check if SIP already ran today (success, market closed, or any outcome)."""
    return _load_budget_data().get("last_run") == date.today().isoformat()


def mark_ran_today():
    """Mark that SIP has run today (in budget file)."""
    data = _load_budget_data()
    data["last_run"] = date.today().isoformat()
    with open(BUDGET_FILE, "w") as f:
        json.dump(data, f)


def _load_history():
    """Load trade history, returning [] on missing/empty/invalid."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                content = f.read().strip()
                return json.loads(content) if content else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def save_trade_history(date_str, budget, reasoning, orders, results):
    """Append today's SIP run to trade history."""
    history = _load_history()

    history.append({
        "date": date_str,
        "budget": budget,
        "reasoning": reasoning,
        "orders": orders,
        "results": results,
    })

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

WEEKLY_BUDGET = DAILY_BUDGET * 5  # 5 trading days
WEEKLY_OVERSPEND_LIMIT = WEEKLY_BUDGET * 0.20  # 20% weekly flex


def get_week_spent():
    """Total amount spent this week (Mon-Fri) from trade history."""
    history = _load_history()
    if not history:
        return 0
    today = date.today()
    monday = today - __import__('datetime').timedelta(days=today.weekday())
    total = 0
    for entry in history:
        entry_date = date.fromisoformat(entry["date"])
        if entry_date >= monday and entry_date <= today:
            for o in entry.get("orders", []):
                if o.get("status") == "OK":
                    total += o.get("quantity", 0) * o.get("ltp", 0)
    return total


SIP_MODEL = "gemini-2.5-flash"


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


def ask_llm_for_allocation(snapshot, budget, max_spend=None):
    """Ask Gemini to decide today's SIP allocation based on portfolio + market conditions."""
    if max_spend is None:
        max_spend = budget
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
- Target budget: Rs.{budget}. You may overspend up to Rs.{int(max_spend)} if there's a strong dip opportunity (20% weekly flex). Calculate carefully.
- Maximize budget utilization — get as close to Rs.{budget} as possible, overspend only when justified by market dips
- You can skip ETFs that are overweight or where market conditions don't favor buying
- Use the LTP values from the portfolio data for cost calculations"""

    response = llm_client.models.generate_content(
        model=SIP_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            thinking_config=types.ThinkingConfig(thinking_budget=2048, include_thoughts=True),
        ),
    )

    text = extract_text(response)

    # Parse JSON from response (handle markdown code blocks, extra text)
    text = text.strip()
    if "```" in text:
        # Extract content between code fences
        parts = text.split("```")
        for part in parts[1::2]:  # odd-indexed parts are inside fences
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    # If still not JSON, try to find the JSON object in the text
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

    log.info(f"LLM raw response: {text[:500]}")
    return json.loads(text)


def run_sip():
    """Run daily SIP. Returns a status message string."""
    log.info("=" * 40)

    if already_ran_today():
        msg = f"SIP already executed today ({date.today().isoformat()}). Skipping."
        log.info(msg)
        print(msg)
        return msg

    # Check if market is open
    if not is_market_open():
        carry = load_carry_forward() + DAILY_BUDGET
        save_carry_forward(carry)
        mark_ran_today()
        log.info(f"Market closed/holiday — carried forward Rs.{DAILY_BUDGET}, total carry Rs.{carry}")
        print(f"Market is closed today. Rs.{DAILY_BUDGET} carried forward (total: Rs.{carry})")
        send_telegram(f"Market closed today. Rs.{DAILY_BUDGET} carried forward (total: Rs.{carry})")
        return

    carry = load_carry_forward()
    budget = DAILY_BUDGET + carry
    # Weekly overspend flex: allow up to 20% overspend across the week
    week_spent = get_week_spent()
    weekly_flex_remaining = max(0, (WEEKLY_BUDGET + WEEKLY_OVERSPEND_LIMIT) - week_spent)
    max_spend = min(budget * 1.2, weekly_flex_remaining)  # up to 20% over daily budget, capped by weekly flex
    log.info(f"SIP run started — daily Rs.{DAILY_BUDGET}, carry Rs.{carry}, effective Rs.{budget}, "
             f"week spent Rs.{week_spent:.0f}, weekly flex remaining Rs.{weekly_flex_remaining:.0f}, max Rs.{max_spend:.0f}")

    # Check funds
    funds = get_fund_limits()
    if funds.get("status") != "success":
        log.error(f"Failed to fetch fund limits: {funds}")
        print(f"ERROR: Could not fetch fund limits: {funds}")
        send_telegram(f"SIP FAILED: Could not fetch fund limits")
        return

    available = float(funds.get("data", {}).get("availabelBalance", 0))
    log.info(f"Available balance: Rs.{available}")

    if available < budget:
        log.warning(f"Insufficient balance Rs.{available} < Rs.{budget}")
        print(f"Insufficient balance Rs.{available:.0f} (need Rs.{budget}), skipping SIP")
        send_telegram(f"SIP SKIPPED: Insufficient balance Rs.{available:.0f} (need Rs.{budget:.0f})")
        return

    # Get portfolio snapshot
    snapshot = get_portfolio_snapshot()
    if snapshot is None:
        print("ERROR: Could not fetch holdings")
        send_telegram("SIP FAILED: Could not fetch holdings")
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
        decision = ask_llm_for_allocation(snapshot, budget, max_spend)
    except Exception as e:
        log.error(f"LLM error: {e}")
        print(f"ERROR: LLM failed — {e}")
        send_telegram(f"SIP FAILED: LLM error — {e}")
        return

    reasoning = decision.get("reasoning", "")
    orders = decision.get("orders", [])

    print(f"\nGemini's reasoning: {reasoning}")
    log.info(f"LLM reasoning: {reasoning}")

    if not orders:
        print("No orders recommended today.")
        send_telegram(f"SIP: No orders recommended today.\n\n_{reasoning}_")
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

    if total_cost > max_spend:
        log.warning(f"LLM exceeded max spend: Rs.{total_cost:.0f} > Rs.{max_spend:.0f}, trimming from end")
        print(f"\n  Over max spend — trimming from lowest priority...")
        # Reduce last order's qty first, drop if needed, then move to next
        while total_cost > max_spend and orders:
            last = orders[-1]
            last_ltp = snapshot.get(last["stock_name"], {}).get("ltp", 1)
            excess = total_cost - max_spend
            reduce_by = min(last["quantity"], int(excess / last_ltp) + 1)
            last["quantity"] -= reduce_by
            total_cost -= reduce_by * last_ltp
            if last["quantity"] <= 0:
                print(f"  Dropped {last['stock_name']}")
                orders.pop()
            else:
                print(f"  Reduced {last['stock_name']} by {reduce_by} to {last['quantity']}")
        if not orders:
            print("  No orders remain after trimming.")
            send_telegram(f"SIP: All orders too expensive for max spend Rs.{max_spend:.0f}")
            return
        print(f"  Adjusted total: Rs.{total_cost:,.0f}")

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
    # Carry forward unspent budget
    actual_spent = sum(
        o["quantity"] * snapshot.get(o["stock_name"], {}).get("ltp", 0)
        for i, o in enumerate(orders)
        if o.get("stock_name") in SIP_ETFS and i < len(results) and results[i] == "OK"
    )
    unspent = budget - actual_spent
    save_carry_forward(max(0, round(unspent, 2)))
    mark_ran_today()
    log.info(f"SIP complete: {succeeded}/{len(results)} orders placed")
    print(f"\nSIP complete: {succeeded}/{len(results)} orders placed")

    # Notify via Telegram
    order_lines = "\n".join(
        f"  {'OK' if (results[i] if i < len(results) else 'SKIP') == 'OK' else 'FAIL'} "
        f"{o['quantity']}x {o['stock_name']} @ Rs.{snapshot.get(o['stock_name'], {}).get('ltp', 0):.2f}"
        for i, o in enumerate(orders) if o.get("stock_name") in SIP_ETFS
    )
    unspent_msg = f"\nUnspent Rs.{unspent:,.0f} carried to tomorrow" if unspent > 0 else ""
    send_telegram(
        f"*SIP Executed* ({date.today().isoformat()})\n"
        f"Budget: Rs.{budget:,.0f} | Spent: Rs.{actual_spent:,.0f}\n"
        f"Orders ({succeeded}/{len(results)}):\n{order_lines}"
        f"{unspent_msg}\n\n"
        f"_{reasoning}_"
    )

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
