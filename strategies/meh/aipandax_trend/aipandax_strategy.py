import yfinance as yf
import pandas as pd
import numpy as np

class AIPandaXStrategy:
    """
    4-Hour Institutional Order Block Mean Reversion Strategy.
    Targets "Mag 7" and BTC.
    """
    
    # Equities-only universe — BTC/ETH removed due to unscaled dollar-magnitude risk
    ASSETS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO", "UNH", "SPY", "QQQ"]
    TIMEFRAME = "4h"

    def __init__(self, volume_multiplier=1.5, wick_ratio=2.0, max_blocks_memory=5, atr_period=14, atr_sl_multiplier=1.5):
        """
        :param volume_multiplier: Multiplier over the 20-period moving average volume to be considered "high".
        :param wick_ratio: Ratio of the wick vs the body to be considered a "violent rejection".
        :param max_blocks_memory: Number of recent active Order Blocks to remember.
        :param atr_period: ATR lookback period for dynamic stop sizing.
        :param atr_sl_multiplier: How many ATRs below/above entry to place the stop loss.
        """
        self.volume_multiplier = volume_multiplier
        self.wick_ratio = wick_ratio
        self.max_blocks_memory = max_blocks_memory
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier

    def calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        """Calculates the 14-period ATR for dynamic stop sizing."""
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=self.atr_period).mean()

    def identify_order_blocks(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Analyzes OHLCV data to find Institutional Order Blocks.
        Returns the DataFrame with Bullish_OB and Bearish_OB boolean columns.
        """
        # Ensure required columns exist
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"DataFrame must contain OHLCV columns: {required_cols}")

        df['Vol_SMA'] = df['Volume'].rolling(window=20).mean()
        df['Body_Size'] = abs(df['Close'] - df['Open'])
        df['Upper_Wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['Lower_Wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']
        df['Candle_Range'] = df['High'] - df['Low']

        # Avoid div by zero
        body_safe = df['Body_Size'].replace(0, 0.0001)

        # Bullish OB: High volume, violent rejection from lows (long lower wick)
        df['Bullish_OB'] = (
            (df['Volume'] > df['Vol_SMA'] * self.volume_multiplier) & 
            ((df['Lower_Wick'] / body_safe) > self.wick_ratio) & 
            (df['Lower_Wick'] > df['Upper_Wick'] * 1.5) & 
            (df['Candle_Range'] > df['Candle_Range'].rolling(20).mean())
        )

        # Bearish OB: High volume, violent rejection from highs (long upper wick)
        df['Bearish_OB'] = (
            (df['Volume'] > df['Vol_SMA'] * self.volume_multiplier) & 
            ((df['Upper_Wick'] / body_safe) > self.wick_ratio) & 
            (df['Upper_Wick'] > df['Lower_Wick'] * 1.5) & 
            (df['Candle_Range'] > df['Candle_Range'].rolling(20).mean())
        )

        return df

    def generate_signals(self, df: pd.DataFrame):
        """
        Generates buy/sell signals on price mean-reverting into standard Institutional Order Blocks.
        Uses ATR-based dynamic stops for proper risk normalization. Applies a strict 3:1 Risk/Reward ratio.
        """
        df = self.identify_order_blocks(df)
        df['ATR'] = self.calculate_atr(df)
        
        active_bull_obs = []  # List of dicts representing active support zones
        active_bear_obs = []  # List of dicts representing active resistance zones
        
        signals = []

        for i in range(len(df)):
            current_low = df['Low'].iloc[i]
            current_high = df['High'].iloc[i]
            current_close = df['Close'].iloc[i]
            current_time = df.index[i]
            current_atr = df['ATR'].iloc[i]
            
            if pd.isna(current_atr):
                continue

            # 1. OB Invalidation: if price closes through the entire OB body, remove it
            active_bull_obs = [ob for ob in active_bull_obs if current_close >= ob['bottom']]
            active_bear_obs = [ob for ob in active_bear_obs if current_close <= ob['top']]
            
            # 2. Check for entries into existing active Order Blocks
            # Mean reversion into Bullish OB
            for ob in active_bull_obs[:]:
                if current_low <= ob['top']:
                    entry_price = ob['top']
                    # ATR-based dynamic stop loss
                    stop_loss = entry_price - (current_atr * self.atr_sl_multiplier)
                    risk = entry_price - stop_loss
                    if risk <= 0: risk = entry_price * 0.001
                    take_profit = entry_price + (risk * 3)  # 3:1 RR
                    
                    signals.append({
                        'timestamp': current_time,
                        'type': 'LONG_ENTRY',
                        'entry': entry_price,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'rr_ratio': 3.0
                    })
                    active_bull_obs.remove(ob)
                    
            # Mean reversion into Bearish OB
            for ob in active_bear_obs[:]:
                if current_high >= ob['bottom']:
                    entry_price = ob['bottom']
                    # ATR-based dynamic stop loss
                    stop_loss = entry_price + (current_atr * self.atr_sl_multiplier)
                    risk = stop_loss - entry_price
                    if risk <= 0: risk = entry_price * 0.001
                    take_profit = entry_price - (risk * 3)  # 3:1 RR
                    
                    signals.append({
                        'timestamp': current_time,
                        'type': 'SHORT_ENTRY',
                        'entry': entry_price,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'rr_ratio': 3.0
                    })
                    active_bear_obs.remove(ob)

            # 2. Add newly formed Order Blocks
            if df['Bullish_OB'].iloc[i]:
                top = max(df['Open'].iloc[i], df['Close'].iloc[i])
                bottom = df['Low'].iloc[i]
                active_bull_obs.append({'top': top, 'bottom': bottom})
                active_bull_obs = active_bull_obs[-self.max_blocks_memory:]

            if df['Bearish_OB'].iloc[i]:
                top = df['High'].iloc[i]
                bottom = min(df['Open'].iloc[i], df['Close'].iloc[i])
                active_bear_obs.append({'top': top, 'bottom': bottom})
                active_bear_obs = active_bear_obs[-self.max_blocks_memory:]
        
        return signals

if __name__ == "__main__":
    print("Strategy Class Available: AIPandaXStrategy")
    print(f"Target Universe: {AIPandaXStrategy.ASSETS}")
    print(f"Target Timeframe: {AIPandaXStrategy.TIMEFRAME}")
