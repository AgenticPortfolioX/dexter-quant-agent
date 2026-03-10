import yfinance as yf
import pandas as pd
import numpy as np
from mean_reversion_strategy import calculate_indicators, identify_band_exhaustion, detect_hidden_divergence, is_reversal_candle, scan_for_entries, calculate_risk_parameters, manage_exit

# Assets: Mix of Forex, Indices, and Commodities suitable for Mean Reversion
ASSETS = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",  # Forex (5)
    "SPY", "QQQ", "IWM",                                         # Indices (3)
    "GLD", "SLV"                                                 # Commodities (2)
]

def fetch_and_prepare_data(ticker, period="2y"):
    """
    Fetches 1h data from yfinance for 2 years and resamples to 4h.
    """
    print(f"Fetching data for {ticker}...")
    try:
        # Fetch 1h data (max 730 days for hourly in yfinance)
        df_1h = yf.download(ticker, period=period, interval="1h", progress=False)
        
        if df_1h.empty:
            print(f"Warning: No data found for {ticker}")
            return None
            
        # Handle MultiIndex columns if present (yfinance update)
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h = df_1h.xs(ticker, axis=1, level=1) if ticker in df_1h.columns.get_level_values(1) else df_1h
            # If xs didn't behave as expected (sometimes it drops level but keeps structure?), force column check
            if 'Close' not in df_1h.columns and df_1h.shape[1] > 5:
                 # Flatten logic might be needed or just assuming standard structure
                 # Let's try to just select the ticker level if it exists
                 pass

        # Resample to 4H
        # Aggregation rules
        agg_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }
        
        # Drop rows with missing data before resample? No, resample handles time gaps.
        df_4h = df_1h.resample('4h').agg(agg_dict).dropna()
        
        if len(df_4h) < 100:
            print(f"Warning: Insufficient 4H data for {ticker} ({len(df_4h)} bars)")
            return None
            
        return df_4h
        
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def run_portfolio_backtest():
    all_trades = []
    
    for ticker in ASSETS:
        df = fetch_and_prepare_data(ticker)
        if df is None: continue
        
        print(f"Processing {ticker} ({len(df)} candles)...")
        debug_mode = False
        
        # --- Run Mean Reversion logic (Similar to run_simulation but returning list) ---
        # Ensure indicators
        df = calculate_indicators(df)
        
        active_position = None
        start_idx = 50
        
        trades_for_ticker = 0
        
        for i in range(start_idx, len(df)):
            current_slice = df.iloc[:i+1]
            current_row = df.iloc[i]
            timestamp = df.index[i]
            
            if active_position:
                status, reason = manage_exit(active_position, current_row)
                
                if status == 'closed_partial':
                    # Log partial exit event if needed, or just update state
                    # We can store a 'partial_exit_time/price' in the dict
                    active_position['partial_exit_time'] = timestamp
                    active_position['partial_exit_price'] = current_row['Close']
                    active_position['status'] = 'partial' # manage_exit does this but good to be explicit
                    
                elif status == 'closed_full':
                    active_position['exit_time'] = timestamp
                    active_position['exit_price'] = current_row['Close']
                    active_position['exit_reason'] = reason
                    active_position['status'] = 'Closed'
                    
                    # Compute PnL
                    # Logic: 
                    # If Partial Hit: 
                    #   PnL1 = 0.5 * Size * (Target1 - Entry) [Long] or (Entry - Target1) [Short]
                    #   PnL2 = 0.5 * Size * (ExitPrice - Entry) [Long] or (Entry - ExitPrice) [Short]
                    # If No Partial (Straight to Stop/Exit):
                    #   PnL = Size * (ExitPrice - Entry) ...
                    
                    entry = active_position['entry_price']
                    exit_p = active_position['exit_price']
                    size = active_position['size']
                    direction = active_position['direction']
                    
                    pnl = 0.0
                    
                    if 'partial_exit_price' in active_position:
                        # Split: 50% at Target1 (Partial Price), 50% at Final Exit
                        partial_price = active_position['target1'] # target1 is strictly the partial price
                        
                        if direction == 'long':
                            pnl1 = (0.5 * size) * (partial_price - entry)
                            pnl2 = (0.5 * size) * (exit_p - entry)
                        else:
                            pnl1 = (0.5 * size) * (entry - partial_price)
                            pnl2 = (0.5 * size) * (entry - exit_p)
                        pnl = pnl1 + pnl2
                    else:
                        # Full size exit
                        if direction == 'long':
                            pnl = size * (exit_p - entry)
                        else:
                            pnl = size * (entry - exit_p)
                            
                    active_position['PnL'] = pnl
                    active_position['Asset'] = ticker
                    
                    all_trades.append(active_position.copy())
                    trades_for_ticker += 1
                    active_position = None
            else:
                signal = scan_for_entries(current_slice, verbose=debug_mode)
                if signal:
                    # Generic account balance $10k per asset for sizing
                    risk_params = calculate_risk_parameters(signal, account_balance=10000, pip_value=1.0)
                    if risk_params and risk_params['valid']:
                        active_position = {
                            'entry_time': timestamp,
                            'direction': signal['direction'],
                            'entry_price': signal['entry_price'],
                            'stop_loss': risk_params['stop_loss'],
                            'target1': risk_params['target1'],
                            'size': risk_params['position_size'],
                            'status': 'open',
                            'Asset': ticker,
                            'Original_Balance': 10000
                        }
        
    # --- Summary ---
    if not all_trades:
        print("No trades executed across all assets.")
        return

    results_df = pd.DataFrame(all_trades)
    
    # Save to Reporting Repo
    import os
    REPORTING_PATH = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\backtests"
    if not os.path.exists(REPORTING_PATH):
        os.makedirs(REPORTING_PATH, exist_ok=True)
        
    output_path = os.path.join(REPORTING_PATH, 'Portfolio_Backtest_Results.csv')
    results_df.to_csv(output_path, index=False)
    print(f"Results saved to: {output_path}")
    
    print("\n=== Backtest Summary (2 Years) ===")
    print(f"Total Trades: {len(results_df)}")
    print(f"Total P&L: ${results_df['PnL'].sum():.2f}")
    print(f"Win Rate: {(results_df['PnL'] > 0).mean():.2%}")
    print("\nPerformance by Asset:")
    print(results_df.groupby('Asset')['PnL'].sum().sort_values(ascending=False))
    
if __name__ == "__main__":
    run_portfolio_backtest()
