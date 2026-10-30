"""
Strategy: Double Break V3 - Elite Scanner
Timeframe: 2-minute
Assets: Top 10 from 30-asset 60d backtest
"""

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
from datetime import datetime, time, timedelta

class DoubleBreakV3Elite:
    def __init__(self):
        self.name = "Double Break V3 (Elite Scanner)"
        self.tickers = ["PYPL", "TSM", "MSFT", "SMCI", "ROKU", "INTC", "WMT", "PG", "AMZN", "META"]
        self.tz = pytz.timezone('US/Eastern')
        
        # Parameters
        self.ema_period = 8
        self.vol_avg_period = 20
        self.body_avg_period = 20
        self.atr_period = 14
        
        # Multipliers
        self.vol_mult = 1.5
        self.body_mult = 1.5
        self.ema_proximity = 0.005 # 0.5%
        self.flag_tightness_ratio = 0.5 # < 50% expansion range
        self.vol_pullback_mult = 0.7 # < 70% avg vol
        self.v_shape_limit = 0.7 # > 70% expansion range is invalid

    def calculate_indicators(self, df):
        df = df.copy()
        df['EMA8'] = df['Close'].ewm(span=self.ema_period, adjust=False).mean()
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR14'] = tr.rolling(window=self.atr_period).mean()
        df['VolAvg20'] = df['Volume'].rolling(window=self.vol_avg_period).mean()
        df['Body'] = abs(df['Close'] - df['Open'])
        df['BodyAvg20'] = df['Body'].rolling(window=self.body_avg_period).mean()
        df['Range'] = df['High'] - df['Low']
        return df

    def calculate_levels(self, data):
        df_2m = data['2m'].copy()
        df_daily = data['daily'].copy()
        df_2m['date'] = df_2m.index.date
        df_daily['date'] = df_daily.index.date
        
        yh_series = pd.Series(index=df_2m.index, dtype=float)
        yl_series = pd.Series(index=df_2m.index, dtype=float)
        pmh_series = pd.Series(index=df_2m.index, dtype=float)
        pml_series = pd.Series(index=df_2m.index, dtype=float)
        
        dates = df_2m['date'].unique()
        for i in range(1, len(dates)):
            curr_date = dates[i]
            prev_date = dates[i-1]
            prev_day_row = df_daily[df_daily['date'] == prev_date]
            if not prev_day_row.empty:
                yh_series[df_2m['date'] == curr_date] = prev_day_row['High'].iloc[0]
                yl_series[df_2m['date'] == curr_date] = prev_day_row['Low'].iloc[0]
            curr_day_2m = df_2m[df_2m['date'] == curr_date]
            pm_data = curr_day_2m.between_time("04:00", "09:29")
            if not pm_data.empty:
                pmh_series[df_2m['date'] == curr_date] = pm_data['High'].max()
                pml_series[df_2m['date'] == curr_date] = pm_data['Low'].min()
                
        df_2m['YH'] = yh_series
        df_2m['YL'] = yl_series
        df_2m['PMH'] = pmh_series
        df_2m['PML'] = pml_series
        return df_2m

    def generate_signals(self, ticker, data):
        df = self.calculate_levels(data)
        df = self.calculate_indicators(df)
        if df.empty or len(df) < 50: return []
        
        signals = []
        session_df = df.between_time("09:30", "15:45")
        breakout_confirmed = False
        breakout_type = None
        breakout_extreme = None
        breakout_idx = -1
        
        for i in range(1, len(session_df)):
            row = session_df.iloc[i]
            if not breakout_confirmed:
                if row['Close'] > row['YH'] or row['Close'] > row['PMH']:
                    if row['Volume'] > self.vol_mult * row['VolAvg20'] and row['Body'] > self.body_mult * row['BodyAvg20']:
                        breakout_confirmed = True; breakout_type = 'LONG'; breakout_idx = i; breakout_extreme = row['High']
                elif row['Close'] < row['YL'] or row['Close'] < row['PML']:
                    if row['Volume'] > self.vol_mult * row['VolAvg20'] and row['Body'] > self.body_mult * row['BodyAvg20']:
                        breakout_confirmed = True; breakout_type = 'SHORT'; breakout_idx = i; breakout_extreme = row['Low']
            else:
                if breakout_type == 'LONG': breakout_extreme = max(breakout_extreme, row['High'])
                else: breakout_extreme = min(breakout_extreme, row['Low'])
                
                if i - breakout_idx > 20: breakout_confirmed = False; continue
                
                near_ema = abs(row['Close'] - row['EMA8']) / row['EMA8'] <= self.ema_proximity
                if near_ema:
                    expansion_range = abs(breakout_extreme - session_df.iloc[breakout_idx]['Low' if breakout_type=='LONG' else 'High'])
                    vol_filter = row['Volume'] < self.vol_pullback_mult * row['VolAvg20']
                    pullback_depth = abs(breakout_extreme - row['Low' if breakout_type=='LONG' else 'High'])
                    v_shape_risk = pullback_depth > self.v_shape_limit * expansion_range
                    
                    if vol_filter and not v_shape_risk:
                        entry_signal = False
                        if breakout_type == 'LONG' and row['Close'] > row['Open'] and (row['Close'] - row['EMA8']) > 0: entry_signal = True
                        elif breakout_type == 'SHORT' and row['Close'] < row['Open'] and (row['Close'] - row['EMA8']) < 0: entry_signal = True
                            
                        if entry_signal:
                            flag_low = session_df.iloc[breakout_idx+1:i+1]['Low'].min()
                            flag_high = session_df.iloc[breakout_idx+1:i+1]['High'].max()
                            sl = flag_low * 0.9999 if breakout_type == 'LONG' else flag_high * 1.0001
                            signals.append({'timestamp': session_df.index[i], 'ticker': ticker, 'type': breakout_type + '_ENTRY', 'entry': row['Close'], 'stop_loss': sl, 'tp1': breakout_extreme})
                            breakout_confirmed = False
        return signals
