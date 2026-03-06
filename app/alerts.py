"""Price alerts and scheduled market updates via Telegram."""
import os
import json
import logging
import time
import threading
from datetime import datetime
from market_data import get_quote, get_market_overview
from portfolio import get_holdings
from notify import send_telegram

log = logging.getLogger("alerts")

ALERTS_FILE = os.path.join(os.path.dirname(__file__), "alerts.json")


def load_alerts():
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE) as f:
            return json.load(f)
    return []


def save_alerts(alerts):
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f, indent=2)


def add_alert(symbol, condition, price, exchange="NSE"):
    """Add a price alert. condition: 'above' or 'below'."""
    alerts = load_alerts()
    alert = {
        "symbol": symbol.upper(),
        "condition": condition,
        "price": float(price),
        "exchange": exchange,
        "created": datetime.now().isoformat(),
        "triggered": False,
    }
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def remove_alert(index):
    """Remove alert by index (0-based)."""
    alerts = load_alerts()
    if 0 <= index < len(alerts):
        removed = alerts.pop(index)
        save_alerts(alerts)
        return removed
    return None


def list_alerts():
    """List all active alerts."""
    alerts = load_alerts()
    active = [a for a in alerts if not a.get("triggered")]
    return {"alerts": active, "total": len(active)}


def check_alerts():
    """Check all alerts against current prices. Returns list of triggered alerts."""
    alerts = load_alerts()
    triggered = []
    changed = False

    for alert in alerts:
        if alert.get("triggered"):
            continue

        quote = get_quote(alert["symbol"], exchange=alert.get("exchange", "NSE"))
        if "error" in quote:
            continue

        current = quote["price"]["close"]
        if current is None:
            continue

        hit = False
        if alert["condition"] == "above" and current >= alert["price"]:
            hit = True
        elif alert["condition"] == "below" and current <= alert["price"]:
            hit = True

        if hit:
            alert["triggered"] = True
            alert["triggered_at"] = datetime.now().isoformat()
            alert["triggered_price"] = current
            triggered.append(alert)
            changed = True

    if changed:
        save_alerts(alerts)

    return triggered


def send_market_update():
    """Send a market overview + portfolio summary to Telegram."""
    overview = get_market_overview()

    lines = ["*Market Update*"]
    for idx, data in overview.items():
        if "close" in data:
            pct = data.get("change_pct", 0)
            arrow = "+" if pct and pct > 0 else ""
            lines.append(f"  {idx}: {data['close']:,.1f} ({arrow}{pct}%)")
        else:
            lines.append(f"  {idx}: unavailable")

    # Portfolio summary
    holdings = get_holdings()
    if holdings.get("status") == "success" and holdings.get("data"):
        total_value = 0
        total_pnl = 0
        for h in holdings["data"]:
            qty = int(h.get("totalQty", 0))
            ltp = float(h.get("lastTradedPrice", 0))
            avg = float(h.get("avgCostPrice", 0))
            total_value += qty * ltp
            total_pnl += qty * (ltp - avg)

        pnl_pct = (total_pnl / (total_value - total_pnl) * 100) if total_value > total_pnl else 0
        lines.append(f"\n*Portfolio*: Rs.{total_value:,.0f} (P&L: Rs.{total_pnl:+,.0f} / {pnl_pct:+.1f}%)")

    send_telegram("\n".join(lines))


def send_alert_notifications(triggered):
    """Send Telegram notifications for triggered alerts."""
    for alert in triggered:
        direction = "crossed above" if alert["condition"] == "above" else "dropped below"
        send_telegram(
            f"*Alert Triggered*\n"
            f"{alert['symbol']} {direction} Rs.{alert['price']:,.2f}\n"
            f"Current: Rs.{alert['triggered_price']:,.2f}"
        )


def run_alert_checker(interval_minutes=5):
    """Run alert checker in a loop. Meant to be called as a thread or standalone."""
    log.info(f"Alert checker started (interval: {interval_minutes}m)")
    while True:
        try:
            triggered = check_alerts()
            if triggered:
                send_alert_notifications(triggered)
                log.info(f"Triggered {len(triggered)} alerts")
        except Exception as e:
            log.error(f"Alert check error: {e}")
        time.sleep(interval_minutes * 60)


def start_alert_thread(interval_minutes=5):
    """Start alert checker as a background daemon thread."""
    t = threading.Thread(target=run_alert_checker, args=(interval_minutes,), daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "update":
        send_market_update()
    elif len(sys.argv) > 1 and sys.argv[1] == "check":
        triggered = check_alerts()
        if triggered:
            send_alert_notifications(triggered)
            print(f"Triggered {len(triggered)} alerts")
        else:
            print("No alerts triggered")
    else:
        # Run continuous alert checker
        run_alert_checker()
