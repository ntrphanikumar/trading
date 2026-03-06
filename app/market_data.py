"""Real-time market data and technical analysis via TradingView."""
from tradingview_ta import TA_Handler, Interval

INTERVAL_MAP = {
    "1m": Interval.INTERVAL_1_MINUTE,
    "5m": Interval.INTERVAL_5_MINUTES,
    "15m": Interval.INTERVAL_15_MINUTES,
    "1h": Interval.INTERVAL_1_HOUR,
    "4h": Interval.INTERVAL_4_HOURS,
    "1d": Interval.INTERVAL_1_DAY,
    "1w": Interval.INTERVAL_1_WEEK,
    "1M": Interval.INTERVAL_1_MONTH,
}

# Common symbol aliases
SYMBOL_ALIASES = {
    "GIFTNIFTY": "NIFTY",
    "GIFT NIFTY": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": "SENSEX",
}


def get_quote(symbol, exchange="NSE", screener="india", interval="1d"):
    """Get real-time quote + technical indicators for a symbol."""
    symbol = symbol.upper().strip()
    symbol = SYMBOL_ALIASES.get(symbol, symbol)
    interval_val = INTERVAL_MAP.get(interval, Interval.INTERVAL_1_DAY)

    try:
        handler = TA_Handler(
            symbol=symbol,
            screener=screener,
            exchange=exchange,
            interval=interval_val,
        )
        analysis = handler.get_analysis()
        ind = analysis.indicators

        return {
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,
            "price": {
                "open": ind.get("open"),
                "high": ind.get("high"),
                "low": ind.get("low"),
                "close": ind.get("close"),
                "volume": ind.get("volume"),
                "change": ind.get("change"),
                "change_pct": round(ind.get("change", 0) / ind.get("open", 1) * 100, 2) if ind.get("open") else None,
            },
            "technicals": {
                "rsi": round(ind.get("RSI", 0), 2),
                "macd": round(ind.get("MACD.macd", 0), 2),
                "macd_signal": round(ind.get("MACD.signal", 0), 2),
                "ema_20": round(ind.get("EMA20", 0), 2),
                "sma_50": round(ind.get("SMA50", 0), 2),
                "sma_200": round(ind.get("SMA200", 0), 2),
                "adx": round(ind.get("ADX", 0), 2),
                "atr": round(ind.get("ATR", 0), 2),
                "bbands_upper": round(ind.get("BB.upper", 0), 2),
                "bbands_lower": round(ind.get("BB.lower", 0), 2),
            },
            "summary": analysis.summary,
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol, "exchange": exchange}


def get_market_overview():
    """Get a snapshot of major Indian market indices."""
    indices = [
        ("NIFTY", "NSE"),
        ("BANKNIFTY", "NSE"),
        ("SENSEX", "BSE"),
        ("CNXMIDCAP", "NSE"),
        ("CNXSMALLCAP", "NSE"),
        ("INDIA VIX", "NSE"),
    ]
    results = {}
    for symbol, exchange in indices:
        try:
            handler = TA_Handler(
                symbol=symbol,
                screener="india",
                exchange=exchange,
                interval=Interval.INTERVAL_1_DAY,
            )
            analysis = handler.get_analysis()
            ind = analysis.indicators
            results[symbol] = {
                "close": ind.get("close"),
                "change": ind.get("change"),
                "change_pct": round(ind.get("change", 0) / ind.get("open", 1) * 100, 2) if ind.get("open") else None,
                "recommendation": analysis.summary.get("RECOMMENDATION"),
            }
        except Exception:
            results[symbol] = {"error": "unavailable"}
    return results
