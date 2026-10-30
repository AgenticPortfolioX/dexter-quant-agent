
import matplotlib.pyplot as plt
import pandas as pd

def plot_le_model_chart(df, ticker, trades_df=None):
    """
    Implements Visualization (Prompt 12):
    - 10m Candles (Simplified Plot via Matplotlib)
    - 8 EMA / 200 EMA (10m)
    - Valid_Long_Touch Diamonds
    - Entry Signals (Green/Red Arrows)
    - Pivot Levels (Annotations)
    - Volume Subplot
    """
    try:
        # Simplified Plotting (Last 5 Days or ~300 bars)
        subset = df.tail(300).copy()
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        
        # 1. Price & EMAs
        ax1.plot(subset.index, subset['Close'], label='Close', color='gray', alpha=0.5)
        ax1.plot(subset.index, subset['EMA_8'], label='EMA 8', color='cyan', linewidth=1)
        ax1.plot(subset.index, subset['EMA_200'], label='EMA 200 (10m)', color='orange', linewidth=2)
        
        # 2. Signals
        # Valid Touch (Diamond)
        valid_longs = subset[subset['Valid_Long_Touch']]
        ax1.scatter(valid_longs.index, valid_longs['Low'] * 0.999, marker='D', color='blue', label='Valid Touch (L)', s=50)
        
        # Entry (Arrow)
        entries_long = subset[subset['Long_Entry_Signal']]
        ax1.scatter(entries_long.index, entries_long['Low'] * 0.998, marker='^', color='green', label='Entry (L)', s=100)
        
        # Pivot Levels (Last known only?)
        # We can annotate the most recent pivot levels found.
        last_pivot_low = subset['Last_Pivot_Low'].iloc[-1]
        ax1.axhline(last_pivot_low, color='green', linestyle='--', alpha=0.3, label=f'Support {last_pivot_low:.2f}')
        
        # 3. Volume
        ax2.bar(subset.index, subset['Volume'], color='gray', alpha=0.3)
        ax2.plot(subset.index, subset['Volume_SMA_20'], color='blue', linewidth=1, label='Vol SMA 20')
        
        # Formatting
        ax1.set_title(f"Le Model Strategy: {ticker} (Last 300 Bars)")
        ax1.legend()
        ax2.legend()
        
        plt.tight_layout()
        plt.savefig(f"{ticker}_le_model.png")
        print(f"Chart saved: {ticker}_le_model.png")
        plt.close()

    except Exception as e:
        print(f"Error Plotting: {e}")
