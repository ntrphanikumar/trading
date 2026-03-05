from client import dhan


def get_holdings():
    """Get all holdings in demat account."""
    return dhan.get_holdings()


def get_positions():
    """Get all open positions for the day."""
    return dhan.get_positions()


def get_fund_limits():
    """Get fund balance and margin information."""
    return dhan.get_fund_limits()
