import robin_stocks.robinhood as r
import pyotp
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta

load_dotenv()

def check_orders():
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    totp_secret = os.getenv("ROBINHOOD_TOTP_SECRET")
    
    if totp_secret:
        totp = pyotp.TOTP(totp_secret).now()
        r.login(username, password, mfa_code=totp)
    else:
        r.login(username, password)
        
    orders = r.get_all_stock_orders()
    today_orders = []
    today = datetime.now().date()
    
    for order in orders:
        order_date = datetime.strptime(order['created_at'].split('T')[0], '%Y-%m-%d').date()
        if order_date == today:
            today_orders.append({
                "symbol": r.get_symbol_by_url(order['instrument']),
                "state": order['state'],
                "side": order['side'],
                "price": order['price'],
                "quantity": order['quantity'],
                "reject_reason": order.get('reject_reason'),
                "cancel_reason": order.get('cancel_reason'),
                "created_at": order['created_at']
            })
            
    print(json.dumps(today_orders, indent=2))

if __name__ == "__main__":
    check_orders()
