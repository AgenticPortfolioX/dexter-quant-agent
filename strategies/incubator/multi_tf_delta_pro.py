"""
Combined Trading Strategy: Multi-TF Signal Scanner + Delta Volume Intelligence Panel
Orchestrator: Antigravity | Worker Agent: Dexter
Role: Elite Quant Strategy Script

Logic:
1. Multi-TF Scanner: Trend (EMAs), RSI (14), StochRSI (21, 5, 5).
2. Delta Panel: Direction, Strength, RelStrength, Session Trend (CumDelta), CVD Divergence, Streak.
3. Entry: Confluence Score (15-20 = Elite).
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime

class MultiTFDeltaPro:
    def __init__(self, symbol="BTC-USD"):
        self.symbol = symbol
        self.tfs = ["5m", "15m", "1h", "4h", "1d"]
        self.chart_tf = "15m"
        self.results_dir = r"C:\Users\jmgra\antigravityagents\.agent\reporting-repo\dexter-quant\backtests"
        if not os.path.exists(self.results_dir): os.makedirs(self.results_dir, exist_ok=True)

    def calculate_indicators(self, df):
        """Standard indicators for the Multi-TF Scanner."""
        # EMAs
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # Trend Direction
        df['Trend'] = np.where(df['EMA20'] > df['EMA50'], 1, -1) # Bull = 1, Bear = -1
        
        # RSI 14
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))
        
        # StochRSI (21, 5, 5)
        period = 21
        k_smooth = 5
        d_smooth = 5
        
        rsi_min = df['RSI'].rolling(window=period).min()
        rsi_max = df['RSI'].rolling(window=period).max()
        df['StochRSI'] = (df['RSI'] - rsi_min) / (rsi_max - rsi_min)
        df['K'] = df['StochRSI'].rolling(window=k_smooth).mean() * 100
        df['D'] = df['K'].rolling(window=d_smooth).mean()
        
        # Stoch Status Icons (Bullish OS = 1, Bearish OB = -1)
        df['Stoch_Status'] = 0
        df.loc[df['K'] < 20, 'Stoch_Status'] = 1 # Oversold
        df.loc[df['K'] > 80, 'Stoch_Status'] = -1 # Overbought
        
        return df

    def calculate_delta_panel(self, df):
        """
        Implements the Delta Volume Intelligence Panel logic.
        Uses VPI (Volume Pressure Index) to simulate Bid/Ask Delta from OHLC.
        """
        # 1. Delta Direction & Strength
        # Formula: (C - O) / (H - L) * Vol
        df['Range'] = df['High'] - df['Low']
        df['Body'] = df['Close'] - df['Open']
        # Avoid division by zero
        df.loc[df['Range'] == 0, 'Range'] = 0.00001
        
        df['Delta'] = (df['Body'] / df['Range']) * df['Volume']
        df['Delta_Ratio'] = abs(df['Delta']) / df['Volume']
        
        # Strength: STRONG if Delta_Ratio > 65%
        df['Strength'] = np.where(df['Delta_Ratio'] > 0.65, 2, 1) # 2=Strong, 1=Moderate
        
        # 2. Relative Strength (vs 14-period avg delta)
        avg_delta = abs(df['Delta']).rolling(window=14).mean()
        df['Rel_Strength'] = abs(df['Delta']) / avg_delta
        
        # 3. Session Trend (Cumulative Delta)
        # Reset daily
        df['Date'] = df.index.date
        df['CumDelta'] = df.groupby('Date')['Delta'].cumsum()
        
        # 4. Streak
        # Count consecutive bars of SAME delta direction
        df['Delta_Dir'] = np.sign(df['Delta'])
        df['Streak'] = df['Delta_Dir'].groupby((df['Delta_Dir'] != df['Delta_Dir'].shift()).cumsum()).cumcount() + 1
        
        # 5. CVD Divergence (Price making new high, CVD not)
        df['Price_Peak'] = df['High'] == df['High'].rolling(window=14).max()
        df['CVD_Peak'] = df['CumDelta'] == df['CumDelta'].rolling(window=14).max()
        df['CVD_Div'] = np.where(df['Price_Peak'] & ~df['CVD_Peak'], -3, 0) # Negative score for divergence
        
        return df

    def get_confluence_score(self, chart_df, multi_tf_data):
        """Calculates the 20-point Confluence Score."""
        # 1. Multi-TF Score (Trend/Stoch alignment)
        chart_df['Score'] = 0
        
        # Check 1H and 4H Bias
        h1 = multi_tf_data['1h']
        h4 = multi_tf_data['4h']
        
        # Mapping higher TF data to 15m (forward fill)
        chart_df = chart_df.join(h1[['Trend', 'Stoch_Status']], rsuffix='_1h', how='left').ffill()
        chart_df = chart_df.join(h4[['Trend', 'Stoch_Status']], rsuffix='_4h', how='left').ffill()
        
        # Trend Confluence
        chart_df.loc[(chart_df['Trend_1h'] == 1) & (chart_df['Trend_4h'] == 1), 'Score'] += 2
        chart_df.loc[(chart_df['Trend_1h'] == -1) & (chart_df['Trend_4h'] == -1), 'Score'] += 2
        
        # Stoch Confluence
        chart_df.loc[(chart_df['Stoch_Status_1h'] == 1) & (chart_df['Stoch_Status_4h'] == 1), 'Score'] += 1
        
        # 2. Delta Score
        chart_df.loc[chart_df['Strength'] == 2, 'Score'] += 3 # STRONG
        chart_df.loc[chart_df['Rel_Strength'] >= 1.5, 'Score'] += 2
        chart_df.loc[chart_df['Streak'] >= 3, 'Score'] += 2
        chart_df.loc[chart_df['CVD_Div'] == -3, 'Score'] -= 5 # Penalty
        
        # Alignment with Session Trend
        chart_df.loc[(chart_df['Delta_Dir'] == 1) & (chart_df['CumDelta'] > 0), 'Score'] += 2
        
        return chart_df

    def fetch_multi_tf(self):
        """Fetches and processes all TFs."""
        data = {}
        for tf in self.tfs:
            df = yf.download(self.symbol, period="60d", interval=tf, progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = self.calculate_indicators(df)
            if tf == self.chart_tf:
                df = self.calculate_delta_panel(df)
            data[tf] = df
        return data

    def run(self):
        print(f"--- INITIALIZING ELITE MULTI-TF DELTA PRO: {self.symbol} ---")
        tf_data = self.fetch_multi_tf()
        chart_df = tf_data[self.chart_tf]
        
        # Apply Confluence Scoring
        chart_df = self.get_confluence_score(chart_df, tf_data)
        
        # Detect Elite Signals
        chart_df['Signal'] = "None"
        chart_df.loc[chart_df['Score'] >= 15, 'Signal'] = "ELITE LONG"
        chart_df.loc[chart_df['Score'] <= -15, 'Signal'] = "ELITE SHORT"
        
        # Reporting
        signals = chart_df[chart_df['Signal'] != "None"]
        print(f"Total Elite Signals Detected: {len(signals)}")
        
        if not signals.empty:
            report_file = os.path.join(self.results_dir, f"MultiTF_Delta_{self.symbol}_Signals.csv")
            signals[['Close', 'Score', 'Signal', 'Strength', 'Rel_Strength', 'Streak']].to_csv(report_file)
            print(f"Detailed signal log: {report_file}")
            
        return chart_df

if __name__ == "__main__":
    bot = MultiTFDeltaPro("BTC-USD")
    bot.run()
