"""MCP server exposing trading tools for OpenClaw integration."""
import sys
import os

# Ensure app directory is on path for local imports
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
from client import dhan
from stocks import search_stocks, find_security_id
from portfolio import get_holdings, get_positions, get_fund_limits
from orders import place_market_order, place_limit_order, get_order_book, get_pending_orders, cancel_order
from market_data import get_quote, get_market_overview
from alerts import add_alert, remove_alert, list_alerts, check_alerts, send_market_update

mcp = FastMCP("dhan-trading")


# --- Portfolio ---

@mcp.tool()
def portfolio_holdings() -> dict:
    """Get all holdings in the demat account (long-term investments)."""
    return get_holdings()


@mcp.tool()
def portfolio_positions() -> dict:
    """Get all open intraday positions for today."""
    return get_positions()


@mcp.tool()
def portfolio_funds() -> dict:
    """Get available fund balance, margin, and account information."""
    return get_fund_limits()


# --- Market Data ---

@mcp.tool()
def quote(symbol: str, exchange: str = "NSE", interval: str = "1d") -> dict:
    """Get real-time price quote and technical indicators (RSI, MACD, EMAs, Bollinger Bands, ADX, ATR) for any stock or index.
    Supports NSE stocks, indices (NIFTY, BANKNIFTY, SENSEX), and ETFs.
    Intervals: 1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M. Use BSE exchange for SENSEX."""
    return get_quote(symbol, exchange=exchange, interval=interval)


@mcp.tool()
def market_overview() -> dict:
    """Get a snapshot of all major Indian market indices — Nifty 50, Bank Nifty, Sensex, Midcap, Smallcap, and India VIX."""
    return get_market_overview()


# --- Stock Search ---

@mcp.tool()
def stock_search(query: str) -> list:
    """Search for stocks by name or company name. Returns matching stock symbols and security IDs."""
    return search_stocks(query)


# --- Orders ---

@mcp.tool()
def order_market(stock_name: str, quantity: int, transaction_type: str, product_type: str = "CNC") -> dict:
    """Place a market order (buy or sell) for a stock. Executes immediately at current market price.
    transaction_type: BUY or SELL. product_type: CNC (delivery) or INTRADAY."""
    return place_market_order(stock_name, quantity, transaction_type, product_type)


@mcp.tool()
def order_limit(stock_name: str, quantity: int, price: float, transaction_type: str, product_type: str = "CNC") -> dict:
    """Place a limit order (buy or sell) for a stock at a specific price.
    transaction_type: BUY or SELL. product_type: CNC (delivery) or INTRADAY."""
    return place_limit_order(stock_name, quantity, price, transaction_type, product_type)


@mcp.tool()
def order_book() -> dict:
    """Get all orders placed today including their status."""
    return get_order_book()


@mcp.tool()
def orders_pending() -> dict:
    """Get only pending/open orders that haven't been executed yet."""
    return get_pending_orders()


@mcp.tool()
def order_cancel(order_id: str) -> dict:
    """Cancel a pending order by its order ID."""
    return cancel_order(order_id)


# --- Alerts ---

@mcp.tool()
def alert_add(symbol: str, condition: str, price: float, exchange: str = "NSE") -> dict:
    """Set a price alert. condition: 'above' (alert when price rises above) or 'below' (alert when price drops below)."""
    return add_alert(symbol, condition, price, exchange)


@mcp.tool()
def alert_remove(index: int) -> dict:
    """Remove a price alert by its index number. Use alert_list first to see indices."""
    result = remove_alert(index)
    return result if result else {"error": "Invalid alert index"}


@mcp.tool()
def alert_list() -> dict:
    """List all active price alerts."""
    return list_alerts()


@mcp.tool()
def alert_check() -> list:
    """Check all alerts against current prices. Returns list of triggered alerts."""
    return check_alerts()


@mcp.tool()
def market_update() -> dict:
    """Send a market overview + portfolio summary to Telegram."""
    send_market_update()
    return {"status": "sent"}


if __name__ == "__main__":
    mcp.run()
