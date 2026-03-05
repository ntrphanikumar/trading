import json
import os

_stocks_cache = None


def _load_stocks():
    global _stocks_cache
    if _stocks_cache is None:
        path = os.path.join(os.path.dirname(__file__), "stocks.json")
        with open(path, "r") as f:
            _stocks_cache = json.load(f).get("companies", [])
    return _stocks_cache


def find_security_id(stock_name):
    """Find security ID by exact stock_name match (case-insensitive)."""
    for stock in _load_stocks():
        if stock.get("stock_name", "").lower() == stock_name.lower():
            return stock["stock_code"]
    return None


def search_stocks(query):
    """Search stocks by substring match on stock_name or company_name."""
    query_lower = query.lower()
    results = []
    for stock in _load_stocks():
        if (query_lower in stock.get("stock_name", "").lower()
                or query_lower in stock.get("company_name", "").lower()):
            results.append({
                "stock_name": stock["stock_name"],
                "company_name": stock["company_name"],
                "stock_code": stock["stock_code"],
            })
    return results
