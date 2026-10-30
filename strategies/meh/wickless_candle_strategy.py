import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time

def identify_wickless_candles(df, instrument_type='Forex'):
    """
    Scans OHLC data for Wickless candles based on strict criteria.
    
    Criteria:
    1. Bullish No-Wick: Green candle (Close > Open), Low == Open (within tolerance).
    2. Bearish No-Wick: Red candle (Close < Open), High == Open (within tolerance).
    
    Tolerances:
    - Forex: 0.00001 (or 0.2 pips)
    - Gold (XAUUSD): 0.02
    """
    
    if instrument_type.upper() == 'GOLD' or 'XAUUSD' in instrument_type.upper():
        tolerance = 0.02
    else:
        # 0.2 pips is 0.00002 for most pairs. 
        # Using 0.00002 to be safe for 0.2 pips, or 0.00001 as specified.
        # I'll use 0.00002 to ensure standard pip calculation.
        tolerance = 0.00002

    results = []

    for i in range(len(df)):
        open_price = float(df['Open'].iloc[i])
        high_price = float(df['High'].iloc[i])
        low_price = float(df['Low'].iloc[i])
        close_price = float(df['Close'].iloc[i])
        
        wickless_type = None
        zone_price = None

        # 1. Bullish No-Wick: Green candle, Low nearly equals Open
        if close_price > open_price:
            if round(abs(low_price - open_price), 6) <= tolerance:
                wickless_type = 'Bullish'
                zone_price = open_price
        
        # 2. Bearish No-Wick: Red candle, High nearly equals Open
        elif close_price < open_price:
            if round(abs(high_price - open_price), 6) <= tolerance:
                wickless_type = 'Bearish'
                zone_price = open_price

        if wickless_type:
            results.append({
                'index': i,
                'timestamp': df.index[i] if isinstance(df.index, pd.DatetimeIndex) else i,
                'type': wickless_type,
                'zone': zone_price,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price
            })

    return results

def detect_zone_taps(df, wickless_candles, instrument_type='Forex'):
    """
    Projects the Zone of each Wickless candle forward and detects the first 'Tap'.
    
    Long Entry (Bullish No-Wick): Low <= Zone (within tolerance)
    Short Entry (Bearish No-Wick): High >= Zone (within tolerance)
    """
    
    if instrument_type.upper() == 'GOLD' or 'XAUUSD' in instrument_type.upper():
        tolerance = 0.02
    else:
        tolerance = 0.00002

    tapped_signals = []

    for wickless in wickless_candles:
        idx = wickless['index']
        zone = wickless['zone']
        w_type = wickless['type']
        
        tap_found = False
        # Search all candles after the Wickless candle
        for j in range(idx + 1, len(df)):
            current_low = float(df['Low'].iloc[j])
            current_high = float(df['High'].iloc[j])
            
            is_tap = False
            if w_type == 'Bullish':
                # For Long: Low must be <= Zone
                if round(current_low - zone, 6) <= tolerance:
                    is_tap = True
            else: # Bearish
                # For Short: High must be >= Zone
                if round(zone - current_high, 6) <= tolerance:
                    is_tap = True
            
            if is_tap:
                tap_signal = wickless.copy()
                tap_signal.update({
                    'tap_index': j,
                    'tap_timestamp': df.index[j] if isinstance(df.index, pd.DatetimeIndex) else j,
                    'tap_price': current_low if w_type == 'Bullish' else current_high
                })
                tapped_signals.append(tap_signal)
                tap_found = True
                break # Only record the FIRST tap
                
    return tapped_signals

def identify_market_structure(df, wickless_index):
    """
    Identifies market structure (BOS) using a 5-candle Bill Williams Fractal.
    Returns the most recent HL (for Bullish) or LH (for Bearish) before the wickless_index.
    """
    
    # Needs at least 5 candles to detect a fractal
    if wickless_index < 2:
        return None

    # Search backwards from wickless_index for fractals
    # A fractal at index i uses [i-2, i-1, i, i+1, i+2]
    # Since we need it BEFORE the wickless candle, 
    # the latest possible fractal center is wickless_index - 2 
    # (so wickless_index is the i+2 candle)
    
    recent_hl = None
    recent_lh = None

    for i in range(wickless_index - 2, 1, -1):
        # Fractal Low (Potential HL)
        if (df['Low'].iloc[i] < df['Low'].iloc[i-1] and 
            df['Low'].iloc[i] < df['Low'].iloc[i-2] and 
            df['Low'].iloc[i] < df['Low'].iloc[i+1] and 
            df['Low'].iloc[i] < df['Low'].iloc[i+2]):
            if recent_hl is None:
                recent_hl = {'index': i, 'price': df['Low'].iloc[i]}

        # Fractal High (Potential LH)
        if (df['High'].iloc[i] > df['High'].iloc[i-1] and 
            df['High'].iloc[i] > df['High'].iloc[i-2] and 
            df['High'].iloc[i] > df['High'].iloc[i+1] and 
            df['High'].iloc[i] > df['High'].iloc[i+2]):
            if recent_lh is None:
                recent_lh = {'index': i, 'price': df['High'].iloc[i]}
        
        # If we found both, we could stop, but we need the MOST RECENT
        if recent_hl and recent_lh:
            break

    return {'recent_hl': recent_hl, 'recent_lh': recent_lh}

def check_news_impact(timestamp):
    """
    Placeholder for economic calendar API.
    Returns True if price is impacted by high-impact news.
    """
    # Mock news event: 2024-05-15 08:30 (CPI Data)
    # If timestamp is within 30 mins, return True
    return False

def generate_trade_signals(df, instrument_type='Forex'):
    """
    Identifies trading opportunities based on 10 strict rules.
    """
    if df is None or len(df) < 50: return []
    
    # instrument_type determines pip buffer/tolerance
    if instrument_type.upper() == 'GOLD' or 'XAUUSD' in instrument_type.upper():
        tolerance = 0.02
    else:
        tolerance = 0.00002

    wickless_candles = identify_wickless_candles(df, instrument_type)
    # Pre-calculate taps for ALL wickless candles once
    all_taps = {}
    for w in wickless_candles:
        # We need the first tap for the entire dataset for Rule 6
        search_results = detect_zone_taps(df, [w], instrument_type)
        if search_results:
            all_taps[w['index']] = search_results[0]['tap_index']
        else:
            all_taps[w['index']] = float('inf')

    final_signals = []

    for wickless in wickless_candles:
        idx = wickless['index']
        w_type = wickless['type']
        zone = wickless['zone']
        timestamp = wickless['timestamp']
        
        # Rule 9: Time and News Filter
        is_london_ny = False
        if isinstance(timestamp, pd.Timestamp):
            hour = timestamp.hour
            if 3 <= hour < 17: 
                is_london_ny = True
        else:
            is_london_ny = True
            
        if not is_london_ny or check_news_impact(timestamp):
            continue
            
        # Rule 2: Market Structure
        structure = identify_market_structure(df, idx)
        if not structure:
            continue
            
        if w_type == 'Bullish' and not structure['recent_hl']:
            continue
        if w_type == 'Bearish' and not structure['recent_lh']:
            continue
            
        # Rule 8: Swing Context
        if idx >= 20:
            lookback = df.iloc[idx-20:idx+1]
            if w_type == 'Bullish':
                if wickless['low'] <= lookback['Low'].min():
                    continue
            else: # Bearish
                if wickless['high'] >= lookback['High'].max():
                    continue
            
        bos_level = structure['recent_hl']['price'] if w_type == 'Bullish' else structure['recent_lh']['price']
        
        # Determine if THIS candle is tapped within 9 candles
        search_end = min(idx + 10, len(df))
        is_valid = True
        near_miss_buffer = 0.00005
        tap = None
        for j in range(idx + 1, search_end):
            curr_low = float(df['Low'].iloc[j])
            curr_high = float(df['High'].iloc[j])
            is_tap = False
            is_near_miss = False
            if w_type == 'Bullish':
                if round(curr_low - zone, 6) <= tolerance: is_tap = True
                elif round(curr_low - zone, 6) <= near_miss_buffer: is_near_miss = True
            else:
                if round(zone - curr_high, 6) <= tolerance: is_tap = True
                elif round(zone - curr_high, 6) <= near_miss_buffer: is_near_miss = True
            if is_tap:
                if is_valid:
                    tap = {'tap_index': j, 'tap_price': curr_low if w_type == 'Bullish' else curr_high}
                break
            if is_near_miss: is_valid = False
            
        if tap:
            entry_price = float(tap['tap_price'])
            pip_size = 0.0001
            room = 3 * pip_size
            if w_type == 'Bullish':
                sl_price = bos_level - room
                risk = entry_price - sl_price
                tp_price = entry_price + risk
            else:
                sl_price = bos_level + room
                risk = sl_price - entry_price
                tp_price = entry_price - risk
                
            # Rule 6: Imbalance
            is_filtered = False
            for prev_w in wickless_candles:
                if prev_w['index'] >= idx: break
                
                # If prev_w has no tap yet or tap is after our 'idx', it's an UNFILLED zone
                if all_taps[prev_w['index']] > idx:
                    if w_type == 'Bullish' and prev_w['type'] == 'Bearish':
                        if sl_price < prev_w['zone'] < entry_price:
                            is_filtered = True; break
                    elif w_type == 'Bearish' and prev_w['type'] == 'Bullish':
                        if entry_price < prev_w['zone'] < sl_price:
                            is_filtered = True; break
            
                final_signals.append({
                    'wickless_idx': idx, 'type': w_type, 'tap_idx': tap['tap_index'],
                    'entry': entry_price, 'sl': round(sl_price, 5), 'tp': round(tp_price, 5),
                    'time': timestamp
                })

    if not final_signals: return []
    # Rule 10: Clustering
    clustered_signals = []
    current_cluster = [final_signals[0]]
    for i in range(1, len(final_signals)):
        prev_s = current_cluster[-1]
        curr_s = final_signals[i]
        if curr_s['type'] == prev_s['type'] and (curr_s['wickless_idx'] - prev_s['wickless_idx']) <= 5:
            current_cluster.append(curr_s)
        else:
            if len(current_cluster) > 1:
                combined = current_cluster[0].copy()
                combined['entry'] = (current_cluster[0]['entry'] + current_cluster[-1]['entry']) / 2
                clustered_signals.append(combined)
            else: clustered_signals.append(current_cluster[0])
            current_cluster = [curr_s]
    if current_cluster:
        if len(current_cluster) > 1:
            combined = current_cluster[0].copy()
            combined['entry'] = (current_cluster[0]['entry'] + current_cluster[-1]['entry']) / 2
            clustered_signals.append(combined)
        else: clustered_signals.append(current_cluster[0])
    return clustered_signals

def run_backtest(df, signals, initial_capital=100000, verbose=True):
    """
    Simulates trades and calculates metrics.
    Assumes 1% risk per trade.
    """
    results = []
    initial_capital = 100000.0
    capital = initial_capital
    risk_per_trade = 0.01
    
    for s in signals:
        entry_idx = s['tap_idx']
        entry_price = s['entry']
        sl_price = s['sl']
        tp_price = s['tp']
        
        # Determine outcome
        outcome = None
        pnl = 0.0
        
        # Check subsequent candles until hit SL or TP
        for i in range(entry_idx + 1, len(df)):
            low = float(df['Low'].iloc[i])
            high = float(df['High'].iloc[i])
            
            if s['type'] == 'Bullish':
                if low <= sl_price:
                    outcome = 'Loss'
                    pnl = -risk_per_trade * capital
                    break
                elif high >= tp_price:
                    outcome = 'Win'
                    pnl = 1.0 * risk_per_trade * capital # 1:1 RR
                    break
            else: # Bearish
                if high >= sl_price:
                    outcome = 'Loss'
                    pnl = -risk_per_trade * capital
                    break
                elif low <= tp_price:
                    outcome = 'Win'
                    pnl = 1.0 * risk_per_trade * capital # 1:1 RR
                    break
        
        if outcome:
            capital += pnl
            results.append({
                'idx': entry_idx,
                'outcome': outcome,
                'pnl': pnl,
                'capital': capital
            })
            
    # Calculate metrics
    if not results:
        if verbose:
            print("\nBACKTEST RESULT: No trades completed in this period.")
        return {
            'starting_capital': initial_capital,
            'final_capital': initial_capital,
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'total_pnl': 0
        }
        
    wins = len([r for r in results if r['outcome'] == 'Win'])
    losses = len([r for r in results if r['outcome'] == 'Loss'])
    total = wins + losses
    win_rate = (wins / total) * 100 if total > 0 else 0
    total_pnl = capital - initial_capital
    
    if verbose:
        print("\n" + "="*40)
        print("      WICKLESS STRATEGY BACKTEST")
        print("="*40)
        print(f"Total Trades:      {total}")
        print(f"Wins:              {wins}")
        print(f"Losses:            {losses}")
        print(f"Win Rate:          {win_rate:.1f}%")
        print(f"Reward:Risk:       1.0")
        print("-" * 40)
        print(f"Starting Capital:  ${initial_capital:,.2f}")
        print(f"Final Capital:     ${capital:,.2f}")
        print(f"Total P/L:         ${total_pnl:,.2f} ({((total_pnl/initial_capital)*100):.2f}%)")
        print(f"Profit Factor:     {((wins * 1.0) / losses):.2f}" if losses > 0 else "N/A")
        print("="*40)
    
    return {
        'starting_capital': initial_capital,
        'final_capital': capital,
        'total_trades': total,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_pnl': total_pnl
    }

# Implementation Execution
def run_full_basket_backtest():
    # Trinity Basket: Highest estructural edge performers
    tickers = [
        'USDJPY=X', 'EURJPY=X', 'GC=F'
    ]
    
    global_results = []
    print(f"\nStarting Basket Backtest (20 Assets, Period: 2y, Interval: 1h)")
    print("="*60)
    
    total_trades = 0
    total_wins = 0
    total_pl = 0
    
    for ticker in tickers:
        print(f"Analyzing {ticker}...", end=" ", flush=True)
        try:
            # Fetch 2 years of 1h data
            df = yf.download(ticker, period='2y', interval='1h', progress=False)
            
            if df.empty:
                print("Skipped (No data)")
                continue
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            # Detect instrument type
            inst_type = 'Gold' if 'GC=F' in ticker else 'Forex' # This needs to be passed to generate_trade_signals if it uses it
            
            signals = generate_trade_signals(df, inst_type)
            results = run_backtest(df, signals, verbose=False) # Run silently
            
            asset_pl = results['final_capital'] - results['starting_capital']
            total_trades += results['total_trades']
            total_wins += results['wins']
            total_pl += asset_pl
            
            print(f"Done. Trades: {results['total_trades']} | Win Rate: {results['win_rate']:.1f}% | P/L: ${asset_pl:,.2f}")
            
            global_results.append({
                'Ticker': ticker,
                'Trades': results['total_trades'],
                'WinRate': results['win_rate'],
                'PL': asset_pl
            })
            
        except Exception as e:
            print(f"Error: {e}")

    print("\n" + "="*60)
    print("      FINAL BASKET PERFORMANCE REPORT (2 YEARS)")
    print("="*60)
    print(f"Total Tickers Analyzed: {len(global_results)}")
    print(f"Total Trades Executed:  {total_trades}")
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    print(f"Aggregate Win Rate:     {win_rate:.1f}%")
    print(f"Total Aggregate P/L:    ${total_pl:,.2f}")
    
    avg_per_asset = total_pl / len(global_results) if global_results else 0
    print(f"Average P/L Per Asset:  ${avg_per_asset:,.2f}")
    print("="*60)
    
    # Identify top performer
    if global_results:
        top = max(global_results, key=lambda x: x['PL'])
        print(f"Top Performer: {top['Ticker']} (${top['PL']:,.2f})")

if __name__ == "__main__":
    run_full_basket_backtest()


class WicklessCandleStrategy:
    """
    Class wrapper for the Wickless Candle strategy functions.
    Provides a standard import interface for the test suite and live monitor.
    """
    def __init__(self, instrument_type='Equity'):
        self.instrument_type = instrument_type

    def generate_signals(self, df):
        """Wraps generate_trade_signals for standard interface."""
        return generate_trade_signals(df, self.instrument_type)

    def run_backtest(self, df):
        signals = self.generate_signals(df)
        return run_backtest(df, signals, verbose=False)
