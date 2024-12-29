from dhanhq import dhanhq
import os
from dotenv import load_dotenv

load_dotenv()
client_id = os.getenv("client_id")
access_token = os.getenv("access_token")
dhan = dhanhq(client_id, access_token)

securities = {
    'PHARMABEES': '4973', 
    'ITBEES': '19084', 
    'BANKBEES': '11439', 
    'MON100': '22739', 
    'SMALLCAP': '22832', 
    'MIDCAPETF': '8413', 
    'GOLDBEES': '14428', 
    'MAFANG': '3507', 
    'HDFCSML250': '14233', 
    'NIFTYBEES': '10576'
}

def nsc_limit_order(symbol, quantity, buy_price):
    return dhan.place_order(security_id=securities[symbol], quantity=quantity, price=buy_price,
        exchange_segment=dhan.NSE, transaction_type=dhan.BUY, order_type=dhan.LIMIT, product_type=dhan.CNC)

def last_traded_price(symbol):
    try:
        return next(filter(lambda h: h['tradingSymbol'] == symbol, dhan.get_holdings()['data']))['lastTradedPrice']
    except Exception as e:
        return 0

# print(last_traded_price('NIFTYBEES'))
print(dhan.get_holdings())
