import yfinance as yf
import json
import sys

tickers = ['ZETA', 'PATH', 'NBIS']
data = {}

for t in tickers:
    try:
        s = yf.Ticker(t)
        # Get last close price
        hist = s.history(period='5d', interval='1d')
        if not hist.empty:
            price = hist['Close'].iloc[-1]
        else:
            price = None
            
        # Get fundamental info
        i = s.info
        
        data[t] = {
            'price': price,
            'pe': i.get('trailingPE'),
            'mkt_cap': i.get('marketCap'),
            'rev_growth': i.get('revenueGrowth'),
            'recommendation': i.get('recommendationKey'),
            'sector': i.get('sector'),
            'industry': i.get('industry')
        }
    except Exception as e:
        data[t] = {"error": str(e)}

json_output = json.dumps(data, indent=2)
print(json_output)
sys.stdout.flush()
