"""
Strategy: Matt-Deep (Trend Flow & Volume Reversal)
Orchestrator: Antigravity | Worker Agent: Dexter
Role: Multi-TF Structural Trend & Delta Volume Validation
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime

class TrendFlowVolumeStrategy:
    def __init__(self, symbol="GOOGL"):
        self.symbol = symbol
        self.exec_tf = "1d" # Optimized for Long-Term structural flow
        self.context_tfs = ["1w", "1m"]
        self.top_assets = ["GOOGL", "HG=F"] # Long-Term Winners
        # Structural settings
        self.delta_lookback = 14
        self.delta_threshold = 0.65 


    def calculate_scanner_indicators(self, df):
        """EMA Stack, RSI, and StochRSI."""
        # EMA Stack (20, 50, 200)
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # Trend Definition: Bull (20>50>200), Bear (20<50<200)
        df['Trend'] = "Neutral"
        df.loc[(df['EMA20'] > df['EMA50']) & (df['EMA50'] > df['EMA200']), 'Trend'] = "Bull"
        df.loc[(df['EMA20'] < df['EMA50']) & (df['EMA50'] < df['EMA200']), 'Trend'] = "Bear"
        
        # RSI 14
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))
        
        # StochRSI (21, 5, 5)
        period = 21
        rsi_min = df['RSI'].rolling(window=period).min()
        rsi_max = df['RSI'].rolling(window=period).max()
        stoch_rsi = ((df['RSI'] - rsi_min) / (rsi_max - rsi_min)).fillna(0)
        df['K'] = stoch_rsi.rolling(window=5).mean() * 100
        
        # Signal Trigger (L/S)
        df['Signal'] = "None"
        # Long: K crosses above 20 + RSI > 30
        df.loc[(df['K'] > 20) & (df['K'].shift(1) <= 20) & (df['RSI'] > 30), 'Signal'] = "L"
        # Short: K crosses below 80 + RSI < 70
        df.loc[(df['K'] < 80) & (df['K'].shift(1) >= 80) & (df['RSI'] < 70), 'Signal'] = "S"
        
        return df

    def calculate_delta_panel(self, df):
        """Delta Panel logic (Direction, Strength, CVD, RelStrength)."""
        # Direction & Strength (VPI Simulation)
        df['Range'] = df['High'] - df['Low']
        df['Body'] = df['Close'] - df['Open']
        df.loc[df['Range'] == 0, 'Range'] = 0.00001
        
        df['Delta'] = (df['Body'] / df['Range']) * df['Volume']
        df['Delta_Ratio'] = abs(df['Delta']) / df['Volume']
        
        # Direction Header
        df['Delta_Dir'] = "MIXED"
        df.loc[df['Delta'] > 0, 'Delta_Dir'] = "BUYERS"
        df.loc[df['Delta'] < 0, 'Delta_Dir'] = "SELLERS"
        
        # Strength: MODERATE/STRONG based on 60% threshold
        df['Strength'] = "WEAK"
        df.loc[df['Delta_Ratio'] > 0.60, 'Strength'] = "MODERATE"
        df.loc[df['Delta_Ratio'] > 0.80, 'Strength'] = "STRONG"
        
        # Relative Strength (Lookback 5 for Scalping)
        avg_delta = abs(df['Delta']).rolling(window=5).mean().replace(0, 0.00001)
        df['Rel_Strength'] = abs(df['Delta']) / avg_delta
        
        # CVD and Divergence
        df['CumDelta'] = df['Delta'].cumsum()
        df['Price_LL'] = df['Low'] == df['Low'].rolling(window=10).min()
        df['CVD_Rising'] = df['CumDelta'] > df['CumDelta'].shift(1)
        
        df['CVD_State'] = "ALIGNED"
        # Bull Div: Price falling, CVD rising
        df.loc[df['Price_LL'] & df['CVD_Rising'], 'CVD_State'] = "BULL DIV"
        # Bear Div: Price rising, CVD falling (Inverse)
        price_hh = df['High'] == df['High'].rolling(window=10).max()
        cvd_falling = df['CumDelta'] < df['CumDelta'].shift(1)
        df.loc[price_hh & cvd_falling, 'CVD_State'] = "BEAR DIV"
        
        return df

    def screen_setups(self):
        print(f"--- SCREENING {self.symbol} FOR TREND FLOW & VOLUME REVERSAL ---")
        
        # 1. Fetch Context TFs (1H/4H)
        context_bias = {}
        for tf in self.context_tfs:
            data = yf.download(self.symbol, period="10d", interval=tf, progress=False, auto_adjust=True)
            if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
            data = self.calculate_scanner_indicators(data)
            context_bias[tf] = data['Trend'].iloc[-1]
            print(f"Context {tf} Trend: {context_bias[tf]}")

        # 2. Fetch Execution TF (15m)
        exec_df = yf.download(self.symbol, period="5d", interval=self.exec_tf, progress=False, auto_adjust=True)
        if isinstance(exec_df.columns, pd.MultiIndex): exec_df.columns = exec_df.columns.get_level_values(0)
        exec_df = self.calculate_scanner_indicators(exec_df)
        exec_df = self.calculate_delta_panel(exec_df)
        
        # 3. Analyze Current Bar (Last 5 bars for context)
        for i in range(-5, 0):
            row = exec_df.iloc[i]
            ts = exec_df.index[i]
            
            # SETUP 1: TREND FLOW
            if row['Signal'] == "L":
                # Check Macro Context
                macro_bull = context_bias['1h'] == "Bull" and context_bias['4h'] == "Bull"
                # Validate Delta
                delta_ok = row['Delta_Dir'] == "BUYERS" and row['Rel_Strength'] > 1.0 and row['CVD_State'] != "BEAR DIV"
                
                if macro_bull and delta_ok:
                    print(f"[{ts}] ELITE LONG DETECTED: Macro Aligned + Delta Confirm ({row['Strength']})")
                elif not delta_ok:
                    print(f"[{ts}] LONG SIGNAL REJECTED: Delta Weakness or Divergence Conflict")

            if row['Signal'] == "S":
                macro_bear = context_bias['1h'] == "Bear" and context_bias['4h'] == "Bear"
                delta_ok = row['Delta_Dir'] == "SELLERS" and row['Rel_Strength'] > 1.0 and row['CVD_State'] != "BULL DIV"
                
                if macro_bear and delta_ok:
                    print(f"[{ts}] ELITE SHORT DETECTED: Macro Aligned + Delta Confirm ({row['Strength']})")
                elif not delta_ok:
                    print(f"[{ts}] SHORT SIGNAL REJECTED: Delta Weakness or Divergence Conflict")

            # SETUP 2: VOLUME REVERSAL (Hidden Divergence)
            if row['CVD_State'] == "BULL DIV" and row['Delta_Dir'] == "BUYERS" and row['Strength'] == "STRONG":
                print(f"[{ts}] VOLUME REVERSAL DETECTED: Strong Hidden Accumulation (CVD Bull Div)")

if __name__ == "__main__":
    scanner = TrendFlowVolumeStrategy("BTC-USD")
    scanner.screen_setups()
