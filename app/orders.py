from client import dhan
from stocks import find_security_id

TRANSACTION_TYPES = {"BUY": dhan.BUY, "SELL": dhan.SELL}
ORDER_TYPES = {"MARKET": dhan.MARKET, "LIMIT": dhan.LIMIT}
PRODUCT_TYPES = {"CNC": dhan.CNC, "INTRADAY": dhan.INTRA}


def place_market_order(stock_name, quantity, transaction_type, product_type="CNC"):
    """Place a market order for a stock by name."""
    security_id = find_security_id(stock_name)
    if not security_id:
        return {"status": "error", "message": f"Stock '{stock_name}' not found"}

    return dhan.place_order(
        security_id=security_id,
        quantity=int(quantity),
        price=0,
        exchange_segment=dhan.NSE,
        transaction_type=TRANSACTION_TYPES.get(transaction_type.upper(), dhan.BUY),
        order_type=dhan.MARKET,
        product_type=PRODUCT_TYPES.get(product_type.upper(), dhan.CNC),
    )


def place_limit_order(stock_name, quantity, price, transaction_type, product_type="CNC"):
    """Place a limit order for a stock by name."""
    security_id = find_security_id(stock_name)
    if not security_id:
        return {"status": "error", "message": f"Stock '{stock_name}' not found"}

    return dhan.place_order(
        security_id=security_id,
        quantity=int(quantity),
        price=float(price),
        exchange_segment=dhan.NSE,
        transaction_type=TRANSACTION_TYPES.get(transaction_type.upper(), dhan.BUY),
        order_type=dhan.LIMIT,
        product_type=PRODUCT_TYPES.get(product_type.upper(), dhan.CNC),
    )


def get_order_book():
    """Get all orders placed today."""
    return dhan.get_order_list()


def get_pending_orders():
    """Get only pending orders."""
    result = dhan.get_order_list()
    if result.get("status") == "success" and result.get("data"):
        pending = [o for o in result["data"] if o.get("orderStatus") == "PENDING"]
        return {"status": "success", "data": pending}
    return result


def cancel_order(order_id):
    """Cancel an order by order ID."""
    return dhan.cancel_order(str(order_id))
