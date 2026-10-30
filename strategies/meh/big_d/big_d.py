"""
BigD Strategy (AMD / PO3) - Live Edition
-------------------------------------------
Classification: LIVE STRATEGY
Assigned Assets: IBIT, ETHE, CLNK
Architecture: Accumulation-Manipulation-Distribution (AMD)
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta
import pytz
import os
import sys
from typing import Dict, List, Optional

class BigDStrategy:
    def __init__(self, symbol: str = "IBIT"):
        self.symbol = symbol
        self.tz = pytz.timezone('US/Eastern')
        self.midnight_open: Optional[float] = None
        self.daily_bias: str = "Neutral"
        self.htf_zones: Dict = {}
        self.pdh: float = 0.0
        self.pdl: float = 0.0
        
    def fetch_data(self, period: str = "2d", interval: str = "5m") -> pd.DataFrame:
        df = yf.download(self.symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty: return df
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if df.index.tz is None: df.index = df.index.tz_localize('UTC')
        df.index = df.index.tz_convert(self.tz)
        return df

    def analyze_daily_bias(self, days: int = 30, df_daily: Optional[pd.DataFrame] = None) -> str:
        if df_daily is None:
            df_daily = yf.download(self.symbol, period=f"{days+10}d", interval="1d", progress=False, auto_adjust=True)
        if df_daily is None or df_daily.empty or len(df_daily) < 2: return "Neutral"
        if isinstance(df_daily.columns, pd.MultiIndex): df_daily.columns = df_daily.columns.get_level_values(0)
        
        self.pdh, self.pdl = df_daily.iloc[-2]['High'], df_daily.iloc[-2]['Low']
        df_daily['ema20'] = df_daily['Close'].ewm(span=20, adjust=False).mean()
        curr_price, curr_ema = df_daily.iloc[-1]['Close'], df_daily.iloc[-1]['ema20']
        
        self.daily_bias = "Bullish" if curr_price > curr_ema else "Bearish"
        return self.daily_bias

    def find_htf_zones(self, df_1h: Optional[pd.DataFrame] = None):
        if df_1h is None:
            df_1h = yf.download(self.symbol, period="10d", interval="1h", progress=False, auto_adjust=True)
        if df_1h is None or df_1h.empty: return
        if isinstance(df_1h.columns, pd.MultiIndex): df_1h.columns = df_1h.columns.get_level_values(0)
        
        self.htf_zones = {'bullish_fvg': [], 'bearish_fvg': []}
        for i in range(2, len(df_1h)):
            c1, c2, c3 = df_1h.iloc[i-2], df_1h.iloc[i-1], df_1h.iloc[i]
            if c3['Low'] > c1['High']: self.htf_zones['bullish_fvg'].append({'top': c3['Low'], 'bottom': c1['High']})
            if c3['High'] < c1['Low']: self.htf_zones['bearish_fvg'].append({'top': c1['Low'], 'bottom': c3['High']})

    def get_midnight_open(self, df: pd.DataFrame, target_date: datetime.date) -> Optional[float]:
        day_data = df[df.index.date == target_date]
        if day_data.empty: return None
        target_time = time(0, 0)
        match = day_data[day_data.index.time == target_time]
        self.midnight_open = match.iloc[0]['Open'] if not match.empty else day_data.iloc[0]['Open']
        return self.midnight_open

    def detect_accumulation(self, df_5m: pd.DataFrame, target_date: datetime.date) -> Dict:
        m_open = self.get_midnight_open(df_5m, target_date)
        if m_open is None: return {'detected': False}
        acc_data = df_5m[(df_5m.index.date == target_date) & (df_5m.index.time <= time(3, 0))]
        if len(acc_data) < 10: return {'detected': False}
        
        acc_high, acc_low = acc_data['High'].max(), acc_data['Low'].min()
        acc_range = acc_high - acc_low
        threshold = m_open * 0.008 
        return {'detected': acc_range < threshold, 'high': acc_high, 'low': acc_low, 'midnight_open': m_open}

    def detect_manipulation(self, df_5m: pd.DataFrame, target_date: datetime.date, acc_result: Dict) -> Dict:
        m_open = acc_result.get('midnight_open')
        if not m_open: return {'detected': False}
        scan_start = datetime.combine(target_date, time(3, 0)).replace(tzinfo=self.tz)
        post_acc_data = df_5m[df_5m.index >= scan_start]
        if post_acc_data.empty: return {'detected': False}
        
        low_levels = [acc_result.get('low'), self.pdl, m_open]
        high_levels = [acc_result.get('high'), self.pdh, m_open]
        atr = (df_5m['High'] - df_5m['Low']).rolling(window=14).mean().iloc[-1]
        sweep_depth = atr * 0.5
        
        for i in range(1, len(post_acc_data)):
            c = post_acc_data.iloc[i]
            for lvl in low_levels:
                if lvl and c['Low'] < (lvl - sweep_depth) and c['Close'] > lvl:
                    return {'detected': True, 'type': 'Bullish', 'sweep_level': c['Low'], 'swept_level': lvl, 'time': post_acc_data.index[i]}
            for lvl in high_levels:
                if lvl and c['High'] > (lvl + sweep_depth) and c['Close'] < lvl:
                    return {'detected': True, 'type': 'Bearish', 'sweep_level': c['High'], 'swept_level': lvl, 'time': post_acc_data.index[i]}
        return {'detected': False}

    def confirm_mss_and_fvg(self, df_5m: pd.DataFrame, manip_result: Dict) -> Dict:
        if not manip_result['detected']: return {'confirmed': False}
        m_time = manip_result['time']
        search_data = df_5m[df_5m.index >= m_time]
        if len(search_data) < 3: return {'confirmed': False}
        
        df_5m['body_size'] = abs(df_5m['Close'] - df_5m['Open'])
        avg_body = df_5m['body_size'].rolling(window=10).mean()
        
        for i in range(1, len(search_data) - 1):
            idx = search_data.index[i]
            all_idx = df_5m.index.get_loc(idx)
            c1, c2, c3 = df_5m.iloc[all_idx-1], df_5m.iloc[all_idx], df_5m.iloc[all_idx+1]
            if c2['body_size'] > (avg_body.loc[idx] * 1.5):
                if manip_result['type'] == 'Bullish':
                    if c2['Close'] > manip_result['swept_level'] and c3['Low'] > c1['High']:
                        return {'confirmed': True, 'direction': 'BUY', 'fvg_top': c3['Low'], 'fvg_bottom': c1['High'], 'time': idx}
                else:
                    if c2['Close'] < manip_result['swept_level'] and c3['High'] < c1['Low']:
                        return {'confirmed': True, 'direction': 'SELL', 'fvg_top': c1['Low'], 'fvg_bottom': c3['High'], 'time': idx}
        return {'confirmed': False}

    def scan(self, df: Optional[pd.DataFrame] = None, df_daily: Optional[pd.DataFrame] = None, df_1h: Optional[pd.DataFrame] = None) -> Optional[Dict]:
        """Main execution entry for Dexter Autotrader."""
        now_et = datetime.now(self.tz)
        if not ((2 <= now_et.hour < 5) or (7 <= now_et.hour < 11)): return None
        
        data = df if df is not None else self.fetch_data(period="2d", interval="5m")
        if data is None or data.empty: return None
        
        self.analyze_daily_bias(df_daily=df_daily)
        self.find_htf_zones(df_1h=df_1h)
        
        acc = self.detect_accumulation(data, now_et.date())
        manip = self.detect_manipulation(data, now_et.date(), acc)
        if not manip['detected']: return None
        
        if manip['type'] == 'Bullish' and self.daily_bias != 'Bullish': return None
        if manip['type'] == 'Bearish' and self.daily_bias != 'Bearish': return None
        
        conf = self.confirm_mss_and_fvg(data, manip)
        if not conf['confirmed']: return None
        
        # --- 2x Leveraged & Inverse Mapping Logic ---
        # 2x Long: BITU (ProShares Ultra Bitcoin ETF)
        # 2x Short: SBIT (ProShares UltraShort Bitcoin ETF)
        LONG_MAP = {"IBIT": "BITU", "BITU": "BITU", "BTC-USD": "BITU", "BTC": "BITU"}
        SHORT_MAP = {"IBIT": "SBIT", "BITU": "SBIT", "BTC-USD": "SBIT", "BTC": "SBIT", "ETHE": "SETH"}
        final_symbol = self.symbol
        final_direction = conf['direction']
        
        # If BUY signal on Bitcoin asset, route to 2x Long BITU
        if final_direction == 'BUY' and self.symbol in LONG_MAP:
            final_symbol = LONG_MAP[self.symbol]
            print(f"  [BigD] Bullish setup on {self.symbol} -> Trading 2x LONG on {final_symbol}")
        # If SELL signal, flip to BUY inverse ETF (2x Short SBIT for Bitcoin)
        elif final_direction == 'SELL' and self.symbol in SHORT_MAP:
            final_symbol = SHORT_MAP[self.symbol]
            final_direction = 'BUY'
            print(f"  [BigD] Bearish setup on {self.symbol} -> Trading 2x SHORT via {final_symbol}")
        
        # Calculate Position (Simple 1% Risk)
        entry = conf['fvg_bottom'] if conf['direction'] == 'BUY' else conf['fvg_top']
        stop = manip['sweep_level']
        risk_dist = abs(entry - stop)
        tp1 = entry + (2 * risk_dist) if conf['direction'] == 'BUY' else entry - (2 * risk_dist)
        
        return {
            'strategy': 'BigD',
            'symbol': final_symbol,
            'direction': final_direction,
            'entry': entry,
            'sl': stop,
            'tp': tp1,
            'timestamp': str(conf['time'])
        }

if __name__ == "__main__":
    import json
    for symbol in ["BITU", "IBIT", "ETHE", "CLNK"]:
        strat = BigDStrategy(symbol)
        signal = strat.scan()
        if signal:
            print(json.dumps(signal, indent=2))
        else:
            print(f"No signal for {symbol}")
