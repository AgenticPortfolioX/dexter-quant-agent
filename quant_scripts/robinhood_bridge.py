import sys
import os
import json
import argparse
import robin_stocks.robinhood as r
import pyotp
from dotenv import load_dotenv

load_dotenv()

def login():
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    totp_secret = os.getenv("ROBINHOOD_TOTP_SECRET")
    
    if not username or not password:
        print(json.dumps({"error": "Missing ROBINHOOD_USERNAME or ROBINHOOD_PASSWORD in .env"}))
        sys.exit(1)
        
    try:
        if totp_secret:
            totp = pyotp.TOTP(totp_secret).now()
            r.login(username, password, mfa_code=totp)
        else:
            r.login(username, password)
        return True
    except Exception as e:
        print(json.dumps({"error": f"Login failed: {str(e)}"}))
        sys.exit(1)

def get_positions():
    login()
    stock_positions = r.build_holdings()
    option_positions = r.get_all_option_positions() # Detailed option positions
    return {"stocks": stock_positions, "options": option_positions}

def get_stock_history(symbol, interval='10minute', span='day'):
    login()
    # interval: '5minute', '10minute', '15minute', '30minute', 'hour', 'day'
    # span: 'day', 'week', 'month', '3month', 'year', '5year'
    history = r.stocks.get_stock_historicals(symbol, interval=interval, span=span)
    return history

def get_crypto_history(symbol, interval='15minute', span='day'):
    login()
    # symbol: e.g. 'ETH'
    history = r.crypto.get_crypto_historicals(symbol, interval=interval, span=span)
    return history

def place_stock_order(symbol, quantity, side, order_type="market", price=None):
    login()
    if side == "buy":
        if order_type == "market":
            res = r.order_buy_market(symbol, quantity, timeInForce='gfd')
        else:
            res = r.order_buy_limit(symbol, quantity, price, timeInForce='gfd')
    else:
        if order_type == "market":
            res = r.order_sell_market(symbol, quantity, timeInForce='gfd')
        else:
            res = r.order_sell_limit(symbol, quantity, price, timeInForce='gfd')
    return res

def place_option_order(symbol, quantity, side, strike, expiry, option_type, order_type="limit", price=None):
    login()
    # expiry format: YYYY-MM-DD
    if side == "buy":
        res = r.order_buy_option_limit(price, symbol, quantity, expiry, strike, option_type)
    else:
        res = r.order_sell_option_limit(price, symbol, quantity, expiry, strike, option_type)
    return res

def main():
    parser = argparse.ArgumentParser(description="Robinhood Trading Bridge")
    parser.add_argument("action", choices=["get_positions", "buy_stock", "sell_stock", "buy_option", "sell_option", "get_stock_history", "get_crypto_history"])
    parser.add_argument("--symbol", help="Stock ticker")
    parser.add_argument("--quantity", type=float, help="Quantity")
    parser.add_argument("--side", choices=["buy", "sell"], help="Buy or Sell")
    parser.add_argument("--order_type", default="market", help="Market or Limit")
    parser.add_argument("--price", type=float, help="Limit price")
    parser.add_argument("--strike", type=float, help="Option strike price")
    parser.add_argument("--expiry", help="Option expiry date (YYYY-MM-DD)")
    parser.add_argument("--option_type", choices=["call", "put"], help="Option type")
    parser.add_argument("--interval", default="15minute", help="History interval")
    parser.add_argument("--span", default="day", help="History span")

    args = parser.parse_args()

    try:
        if args.action == "get_positions":
            result = get_positions()
        elif args.action == "get_stock_history":
            result = get_stock_history(args.symbol, args.interval, args.span)
        elif args.action == "get_crypto_history":
            result = get_crypto_history(args.symbol, args.interval, args.span)
        elif args.action in ["buy_stock", "sell_stock"]:
            side = "buy" if args.action == "buy_stock" else "sell"
            result = place_stock_order(args.symbol, args.quantity, side, args.order_type, args.price)
        elif args.action in ["buy_option", "sell_option"]:
            side = "buy" if args.action == "buy_option" else "sell"
            result = place_option_order(args.symbol, args.quantity, side, args.strike, args.expiry, args.option_type, "limit", args.price)
        
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
