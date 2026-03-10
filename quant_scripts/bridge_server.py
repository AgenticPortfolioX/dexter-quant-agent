
import os
import json
from flask import Flask, request, jsonify
import robin_stocks.robinhood as r
import pyotp
import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Persistent login state
is_logged_in = False

def login_to_robinhood():
    global is_logged_in
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    totp_secret = os.getenv("ROBINHOOD_TOTP_SECRET")
    
    if not username or not password:
        print("Error: Missing credentials in .env")
        return False
        
    try:
        if totp_secret:
            totp = pyotp.TOTP(totp_secret).now()
            r.login(username, password, mfa_code=totp)
        else:
            r.login(username, password)
        is_logged_in = True
        print("Login successful.")
        return True
    except Exception as e:
        print(f"Login failed: {e}")
        return False

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "online",
        "logged_in": is_logged_in
    })

@app.route('/positions', methods=['GET'])
def get_positions():
    if not is_logged_in:
        if not login_to_robinhood():
            return jsonify({"error": "Login failed"}), 500
    try:
        stock_positions = r.build_holdings()
        option_positions = r.get_all_option_positions()
        return jsonify({"stocks": stock_positions, "options": option_positions})
    except Exception as e:
        if login_to_robinhood():
             stock_positions = r.build_holdings()
             option_positions = r.get_all_option_positions()
             return jsonify({"stocks": stock_positions, "options": option_positions})
        return jsonify({"error": str(e)}), 500

@app.route('/cash', methods=['GET'])
def get_cash_info():
    if not is_logged_in:
        if not login_to_robinhood():
            return jsonify({"error": "Login failed"}), 500
    try:
        profile = r.load_account_profile()
        return jsonify({
            "type": profile.get("type"),
            "portfolio_cash": profile.get("portfolio_cash"),
            "cash_available_for_withdrawal": profile.get("cash_available_for_withdrawal"),
            "cash_held_for_orders": profile.get("cash_held_for_orders"),
            "unsettled_funds": profile.get("unsettled_funds")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history', methods=['GET'])
def get_history():
    if not is_logged_in:
        if not login_to_robinhood():
            return jsonify({"error": "Login failed"}), 500
    
    symbol = request.args.get("symbol")
    asset_type = request.args.get("type", "stock")
    interval = request.args.get("interval", "10minute")
    span = request.args.get("span", "day")
    
    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400
        
    try:
        if asset_type == "crypto":
            history = r.crypto.get_crypto_historicals(symbol, interval=interval, span=span)
        else:
            history = r.stocks.get_stock_historicals(symbol, interval=interval, span=span)
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/order', methods=['POST'])
def place_order():
    if not is_logged_in:
        if not login_to_robinhood():
            return jsonify({"error": "Login failed"}), 500
    
    data = request.json
    asset_type = data.get("type", "stock")
    action = data.get("action")
    symbol = data.get("symbol")
    quantity = float(data.get("quantity", 0))
    order_type = data.get("order_type", "market")
    price = data.get("price")
    
    expiry = data.get("expiry")
    strike = data.get("strike")
    option_type = data.get("option_type")

    try:
        if asset_type == "stock":
            if action == "buy":
                res = r.order_buy_market(symbol, quantity, timeInForce='gfd') if order_type == "market" else r.order_buy_limit(symbol, quantity, price, timeInForce='gfd')
            elif action == "sell":
                res = r.order_sell_market(symbol, quantity, timeInForce='gfd') if order_type == "market" else r.order_sell_limit(symbol, quantity, price, timeInForce='gfd')
            else:
                return jsonify({"error": "Invalid action"}), 400
        elif asset_type == "option":
            res = r.order_buy_option_limit(price, symbol, quantity, expiry, strike, option_type) if action == "buy" else r.order_sell_option_limit(price, symbol, quantity, expiry, strike, option_type)
        else:
            return jsonify({"error": "Invalid asset type"}), 400
            
        log_file = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent\logs\bridge_raw.log"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "a") as f:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{now_str}] Order Request for {symbol}: {json.dumps(data)}\n")
            f.write(f"[{now_str}] Order Response: {json.dumps(res)}\n")

        if isinstance(res, dict) and (res.get('detail') == 'Authentication credentials were not provided.' or 'error' in str(res).lower()):
             if login_to_robinhood():
                 return place_order() 
        
        error_keys = ['non_field_errors', 'detail', 'reject_reason', 'error']
        if isinstance(res, dict) and any(res.get(k) is not None for k in error_keys):
            return jsonify(res), 400

        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    login_to_robinhood()
    app.run(host='0.0.0.0', port=5005)
