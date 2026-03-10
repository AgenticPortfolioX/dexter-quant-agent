import yfinance as yf
import pandas as pd
import os
from wickless_candle_strategy import generate_trade_signals, run_backtest

# Define the 30 logical assets
ASSETS = [
    # Forex (10)
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", 
    "USDCHF=X", "NZDUSD=X", "EURJPY=X", "GBPJPY=X", "EURGBP=X",
    # Indices (6)
    "SPY", "QQQ", "IWM", "DIA", "^GSPC", "^IXIC",
    # Commodities (3)
    "GC=F", "SI=F", "CL=F",
    # Crypto (3)
    "BTC-USD", "ETH-USD", "SOL-USD",
    # Equities (8)
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "JPM"
]

def run_bulk_backtest():
    results_list = []
    
    print("\n" + "="*60)
    print("      WICKLESS CANDLE BULK BACKTEST (2 YEARS, 1H)")
    print("="*60)
    
    for ticker in ASSETS:
        print(f"Processing {ticker}...", end=" ", flush=True)
        try:
            # Fetch 2 years of 1h data
            df = yf.download(ticker, period='2y', interval='1h', progress=False)
            
            if df.empty:
                print("FAILED (No data)")
                continue
                
            # Handle MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Determine instrument type
            if any(x in ticker for x in ['GC=F', 'SI=F', 'CL=F', 'XAUUSD']):
                inst_type = 'Gold' 
            else:
                inst_type = 'Forex'
            
            # Run strategy
            signals = generate_trade_signals(df, inst_type)
            metrics = run_backtest(df, signals, verbose=False)
            
            if metrics:
                metrics['Ticker'] = ticker
                results_list.append(metrics)
                print(f"DONE. Trades: {metrics['total_trades']} | Win Rate: {metrics['win_rate']:.1f}% | P/L: ${metrics['total_pnl']:,.2f}")
            else:
                print("DONE. No trades.")
                
        except Exception as e:
            print(f"ERROR: {e}")

    if not results_list:
        print("\nNo results gathered.")
        return

    # Create Summary DataFrame
    summary_df = pd.DataFrame(results_list)
    cols = ['Ticker', 'total_trades', 'wins', 'losses', 'win_rate', 'total_pnl']
    summary_df = summary_df[cols]
    
    # Save to CSV
    import os
    REPORTING_PATH = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\backtests"
    if not os.path.exists(REPORTING_PATH):
        os.makedirs(REPORTING_PATH, exist_ok=True)
        
    output_file = os.path.join(REPORTING_PATH, 'Wickless_Backtest_Results.csv')
    summary_df.to_csv(output_file, index=False)
    
    # Final Aggregate Report
    print("\n" + "="*60)
    print("      FINAL AGGREGATE PERFORMANCE REPORT")
    print("="*60)
    print(f"Total Assets Backtested: {len(results_list)}")
    print(f"Total Trades Executed:   {summary_df['total_trades'].sum()}")
    avg_win_rate = summary_df[summary_df['total_trades'] > 0]['win_rate'].mean()
    print(f"Average Win Rate:        {avg_win_rate:.1f}%")
    print(f"Total Net P/L:           ${summary_df['total_pnl'].sum():,.2f}")
    
    top_performer = summary_df.loc[summary_df['total_pnl'].idxmax()]
    print(f"Top Performer:           {top_performer['Ticker']} (${top_performer['total_pnl']:,.2f})")
    print(f"Results saved to:        {output_file}")
    print("="*60)

if __name__ == "__main__":
    run_bulk_backtest()
