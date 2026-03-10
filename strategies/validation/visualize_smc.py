
import pandas as pd
import numpy as np
import os
import sys
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

from strategies.incubator.smc_btc_plus import SmartMoneyStrategy

def visualize_smc():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'incubator')
    ticker = "ES"
    
    df_5m_path = os.path.join(data_dir, f"{ticker}_5m_smc.pkl")
    if not os.path.exists(df_5m_path):
        print("Data not found.")
        return
        
    df = pd.read_pickle(df_5m_path)
    
    # Process Strategy
    strategy = SmartMoneyStrategy()
    df = strategy.add_indicators(df)
    df = strategy.process_logic(df)
    
    # Take last 3 days for visualization as requested
    # Data is approx 5 days, so last 3 days
    start_time = df.index.max() - pd.Timedelta(days=3)
    pdf = df[df.index >= start_time].copy()
    
    fig, ax = plt.subplots(figsize=(16, 8))
    
    # Plot Price
    ax.plot(pdf.index, pdf['Close'], label='Close', color='gray', alpha=0.5)
    
    # 1. Swing Highs/Lows (Dots)
    sw_highs = pdf[pdf['swing_high'].notna()]
    sw_lows = pdf[pdf['swing_low'].notna()]
    ax.scatter(sw_highs.index, sw_highs['swing_high'], color='red', marker='v', label='Confirmed Swing High', s=30)
    ax.scatter(sw_lows.index, sw_lows['swing_low'], color='blue', marker='^', label='Confirmed Swing Low', s=30)
    
    # 2. Displacement (Yellow)
    disp = pdf[pdf['is_displacement'] == True]
    ax.scatter(disp.index, disp['High'] + 1, color='yellow', marker='*', label='Displacement', s=50)
    
    # 3. FVG (Shade)
    # Bullish FVG
    bull_fvgs = pdf[pdf['bullish_fvg_top'].notna()]
    for idx, row in bull_fvgs.iterrows():
        # Gap is between i-1 High and i+1 Low. 
        # In our logic stored at i, bullish_fvg_top = High[i-1]. 
        # And Low[i+1] > High[i-1]. So gap is [High[i-1], Low[i+1]]
        # We need the High[i-1] and Low[i+1]. I'll re-calculate for visual accuracy.
        i_pos = df.index.get_loc(idx)
        gap_bot = df.iloc[i_pos-1]['High']
        gap_top = df.iloc[i_pos+1]['Low']
        
        # Rectangle
        rect = patches.Rectangle((idx, gap_bot), pd.Timedelta(minutes=5), gap_top-gap_bot, 
                                 linewidth=0, edgecolor='none', facecolor='green', alpha=0.3)
        ax.add_patch(rect)

    # Bearish FVG
    bear_fvgs = pdf[pdf['bearish_fvg_bottom'].notna()]
    for idx, row in bear_fvgs.iterrows():
        i_pos = df.index.get_loc(idx)
        gap_top = df.iloc[i_pos-1]['Low']
        gap_bot = df.iloc[i_pos+1]['High']
        
        rect = patches.Rectangle((idx, gap_bot), pd.Timedelta(minutes=5), gap_top-gap_bot, 
                                 linewidth=0, edgecolor='none', facecolor='red', alpha=0.3)
        ax.add_patch(rect)

    # 4. MSS (Arrows)
    mss_bull = pdf[pdf['mss_signal'] == 'Bullish MSS']
    mss_bear = pdf[pdf['mss_signal'] == 'Bearish MSS']
    for idx, row in mss_bull.iterrows():
        ax.annotate('', xy=(idx, row['Low'] - 2), xytext=(idx, row['Low'] - 5),
                    arrowprops=dict(facecolor='green', shrink=0.05, width=2, headwidth=8))
    for idx, row in mss_bear.iterrows():
        ax.annotate('', xy=(idx, row['High'] + 2), xytext=(idx, row['High'] + 5),
                    arrowprops=dict(facecolor='red', shrink=0.05, width=2, headwidth=8))
                    
    # 5. Entry Signals (Large Arrows)
    entry_buy = pdf[pdf['entry_signal'] == 'BUY']
    entry_sell = pdf[pdf['entry_signal'] == 'SELL']
    label_buy_added = False
    for idx, row in entry_buy.iterrows():
        label = 'BUY Entry' if not label_buy_added else ""
        ax.scatter(idx, row['Low'] - 3, color='green', marker='P', s=100, label=label)
        label_buy_added = True
        
    label_sell_added = False
    for idx, row in entry_sell.iterrows():
        label = 'SELL Entry' if not label_sell_added else ""
        ax.scatter(idx, row['High'] + 3, color='red', marker='X', s=100, label=label)
        label_sell_added = True

    ax.set_title(f"SMC Strategy Visualization - {ticker} (5m)")
    ax.legend()
    
    output_path = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\backtest_results\smc_chart.png"
    plt.savefig(output_path)
    print(f"Chart saved to {output_path}")

if __name__ == "__main__":
    visualize_smc()
