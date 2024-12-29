from dhanhq import dhanhq
import requests
import os
from dotenv import load_dotenv

load_dotenv()
client_id = os.getenv("client_id")
access_token = os.getenv("access_token")

def fetch_security_info(security_id, access_token):
    API_ENDPOINT = f"https://api.dhan.co/marketdata/security/{security_id}"
    HEADERS = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(API_ENDPOINT, headers=HEADERS)
    return response.json() if response.status_code == 200 else response.json()

# Usage
security_id = "NIFTYBEES"
# access_token = "YOUR_ACCESS_TOKEN"
# info = fetch_security_info(security_id, access_token)
# print("Security Info:", info)


dhan = dhanhq(client_id, access_token)

holdings = dhan.get_holdings()
print(holdings)

# securities = dhan.fetch_security_list()
# print(securities)

# niftybees = dhan.place_order(security_id='10576',           # Nifty PE
#     exchange_segment=dhan.NSE,
#     transaction_type=dhan.BUY,
#     quantity=550,
#     order_type=dhan.MARKET,
#     product_type=dhan.CNC,
#     price=10)
# print(niftybees)

# print(dhan.ticker_data({"NSE_EQ": [10576]}))


# # Place an order for Equity Cash
# dhan.place_order(security_id='1333',            # HDFC Bank
#     exchange_segment=dhan.NSE,
#     transaction_type=dhan.BUY,
#     quantity=10,
#     order_type=dhan.MARKET,
#     product_type=dhan.INTRA,
#     price=0)
    
# # Place an order for NSE Futures & Options
# dhan.place_order(security_id='52175',           # Nifty PE
#     exchange_segment=dhan.NSE_FNO,
#     transaction_type=dhan.BUY,
#     quantity=550,
#     order_type=dhan.MARKET,
#     product_type=dhan.INTRA,
#     price=0)
  
# # Fetch all orders
# dhan.get_order_list()

# # Get order by id
# dhan.get_order_by_id(order_id)

# # Modify order
# dhan.modify_order(order_id, order_type, leg_name, quantity, price, trigger_price, disclosed_quantity, validity)

# # Cancel order
# dhan.cancel_order(order_id)

# # Get order by correlation id
# dhan.get_order_by_corelationID(corelationID)

# # Get Instrument List
# dhan.fetch_security_list("compact")

# # Get positions
# dhan.get_positions()

# # Get holdings
# dhan.get_holdings()

# # Intraday Minute Data
# dhan.intraday_minute_data(security_id,exchange_segment,instrument_type)

# # Historical Daily Data
# dhan.historical_daily_data(security_id,exchange_segment,instrument_type,expiry_code,from_date,to_date)

# # Time Converter
# dhan.convert_to_date_time(EPOCH Date)

# # Get trade book
# dhan.get_trade_book(order_id)

# # Get trade history
# dhan.get_trade_history(from_date,to_date,page_number=0)

# # Get fund limits
# dhan.get_fund_limits()

# # Generate TPIN
# dhan.generate_tpin()

# # Enter TPIN in Form
# dhan.open_browser_for_tpin(isin='INE00IN01015',
#     qty=1,
#     exchange='NSE')

# # EDIS Status and Inquiry
# dhan.edis_inquiry()

# # Expiry List of Underlying
# dhan.expiry_list(
#     under_security_id=13,                       # Nifty
#     under_exchange_segment="IDX_I"
# )

# # Option Chain
# dhan.option_chain(
#     under_security_id=13,                       # Nifty
#     under_exchange_segment="IDX_I",
#     expiry="2024-10-31"
# )

# # Market Quote Data                     # LTP - ticker_data, OHLC - ohlc_data, Full Packet - quote_data
# dhan.ohlc_data(
#     securities = {"NSE_EQ":[1333]}
# )

# # Place Forever Order (SINGLE)
# dhan.place_forever(
#     security_id="1333",
#     exchange_segment= dhan.NSE,
#     transaction_type= dhan.BUY,
#     product_type=dhan.CNC,
#     product_type= dhan.LIMIT,
#     quantity= 10,
#     price= 1900,
#     trigger_Price= 1950
# )