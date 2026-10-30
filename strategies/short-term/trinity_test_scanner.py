import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import sys

# Add current dir to sys.path to find the strategy module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from wickless_candle_strategy import generate_trade_signals

def run_trinity_scan():
    # Pivot to Robinhood-tradable ETFs for the Trinity Basket
    # GLD (Gold), FXY (Japanese Yen), FXE (Euro)
    trinity_assets = ["GLD", "FXY", "FXE"]
    all_recent_signals = []
    
    # Reference stats for the board (Updated for ETFs)
    trinity_stats = {
        "FXY": {"win_rate": "62.9%", "pf": "5.08", "strength": "HIGH"},
        "FXE": {"win_rate": "66.7%", "pf": "6.00", "strength": "ELITE"},
        "GLD": {"win_rate": "54.8%", "pf": "3.64", "strength": "STABLE"}
    }
    print(f"============================================================")
    print(f"      TRINITY BASKET SCANNER (Forward Testing Phase)        ")
    print(f"      Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S EST')} ")
    print(f"============================================================\n")
    
    for ticker in trinity_assets:
        print(f"Scanning {ticker} (Last 10 Days, 1h Interval)...")
        try:
            # Fetch 1h data
            df = yf.download(ticker, period="10d", interval="1h", progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            if df.empty:
                print(f"  [!] No data for {ticker}")
                continue
            
            # Use the strategy to find signals
            signals = generate_trade_signals(df)
            
            # Find signals in the last 24 hours
            cutoff = datetime.now() - timedelta(hours=24)
            found_signal_for_ticker = False
            for s in signals:
                # Ensure we handle timezone-aware vs naive comparisons
                s_time = s['time']
                if s_time.tzinfo is not None:
                    cutoff_aware = cutoff.replace(tzinfo=s_time.tzinfo)
                else:
                    cutoff_aware = cutoff
                
                if s_time > cutoff_aware:
                    s['ticker'] = ticker
                    all_recent_signals.append(s)
                    print(f"  [+] Found signal for {ticker} at {s['time']}")
                    found_signal_for_ticker = True
            
            if not found_signal_for_ticker:
                print(f"  [-] No signals in the last 24 hours.")

        except Exception as e:
            print(f"  [!] Error scanning {ticker}: {e}")
            
    print(f"\n============================================================")
    
    # --- Smart-Merge Update for LIVE_Strategy_BOARD.md ---
    board_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LIVE_Strategy_BOARD.md")
    
    # Defaults in case file is missing or corrupted
    section1_content = "# 🏦 ALPHA COMMAND CENTER: LIVE STRATEGY BOARD\n**Status: OPERATIONAL**\n\n---\n\n## 🚀 SECTION 1: REAL-MONEY CAPITAL ALLOCATION (SMC)\n| Asset | Status |\n| :--- | :--- |\n| **SMC Portfolio** | ACTIVE |\n\n---\n\n"
    footer_content = "\n---\n\n## 🛠️ System Configuration\n- **Wickless Engine**: 10 Rules\n- **Interval**: 1h\n"

    if os.path.exists(board_path):
        try:
            with open(board_path, "r", encoding='utf-8') as f:
                full_text = f.read()
            
            # Split to preserve everything before Section 2
            if "## 🛰️ SECTION 2" in full_text:
                section1_content = full_text.split("## 🛰️ SECTION 2")[0]
                
                # Split everything from "Benchmarks" onwards to keep the footer
                if "## 📊 Performance Benchmarks" in full_text:
                    footer_content = "\n---\n\n## 📊 Performance Benchmarks" + full_text.split("## 📊 Performance Benchmarks")[1]
        except Exception as e:
            print(f"  [!] Error reading board for merge: {e}")

    with open(board_path, "w", encoding='utf-8') as f:
        f.write(section1_content)
        f.write("## 🛰️ SECTION 2: TRINITY STRATEGY (FORWARD-TESTING)\n")
        f.write("**Environment**: PAPER / SCANNER | **Strategy**: Wickless Candle v14.2\n\n")
        f.write(f"*Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M EST')}*\n\n")
        f.write("| Asset | Signal Type | Entry Level | Stop Loss | Take Profit | Execution | Timestamp (UTC) |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        
        if all_recent_signals:
            for s in all_recent_signals:
                ticker = s['ticker']
                # Check for Inverse Mapping if Short Signal
                if s['type'] == 'Bearish':
                    inverse_map = {
                        "SPY": "SH",     # Inverse S&P 500
                        "QQQ": "PSQ",    # Inverse Nasdaq
                        "DIA": "DOG",    # Inverse Dow
                        "IWM": "RWM",    # Inverse Russell 2000
                        "AAPL": "AAPL PUT",
                        "GS": "GS PUT"
                    }
                    if ticker in inverse_map:
                        target = inverse_map[ticker]
                        etype = "Inverse ETF" if "PUT" not in target else "Option"
                    else:
                        target = f"{ticker} PUT"
                        etype = "Option"
                else:
                    target = ticker
                    etype = "Equity"

                f.write(f"| **{ticker}** | {s['type']} | {s['entry']:.5f} | {s['sl']:.5f} | {s['tp']:.5f} | {target} ({etype}) | {s['time']} |\n")
        else:
            f.write("| **FXY** | No Signal | - | - | - | Scanning... | - |\n")
            f.write("| **FXE** | No Signal | - | - | - | Scanning... | - |\n")
            f.write("| **GLD** | No Signal | - | - | - | Scanning... | - |\n")
            
        f.write(footer_content)

    if all_recent_signals:
        print(f"SUMMARY: {len(all_recent_signals)} ACTIVE/RECENT SIGNALS")
        for s in all_recent_signals:
            print(f"--- {s['ticker']} ---")
            print(f"  Type:  {s['type']}")
            print(f"  Entry: {s['entry']:.5f}")
            print(f"  SL:    {s['sl']:.5f}")
            print(f"  TP:    {s['tp']:.5f}")
            print(f"  Status: Valid as of {s['time']}")
    else:
        print("SUMMARY: No recent signals found across Trinity Basket.")
    print(f"============================================================")

if __name__ == "__main__":
    run_trinity_scan()
