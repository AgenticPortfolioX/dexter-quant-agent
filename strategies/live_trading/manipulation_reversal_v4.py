"""
Strategy: Manipulation Reversal V4
Timeframe: 15-minute
Window: 09:30 - 11:00 EST
Logic: Manipulation candle sweep at key Volume Profile levels (POC, VAH, VAL).
"""

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
from datetime import datetime, time, timedelta

class ManipulationReversalV4:
    def __init__(self):
        self.name = "Manipulation Reversal V4"
        self.assets = ["TSLA", "AMD", "V", "UNH", "PLTR", "GOOGL", "JPM", "IWM", "SPY", "CVX"]
        self.tz = pytz.timezone('US/Eastern')
        self.window_start = time(9, 30)
        self.window_end = time(11, 0)
        self.vp_reset_hour = 18 # 6 PM EST previous day
        self.proximity_threshold = 0.0005 # 0.05%
        self.min_rr = 3.0
        self.vol_area_ratio = 0.70

    def calculate_vp_levels(self, df_15m, current_time):
        target_date = current_time.date()
        if current_time.time() < time(self.vp_reset_hour, 0):
            start_date = target_date - timedelta(days=1)
        else:
            start_date = target_date
        start_ts = self.tz.localize(datetime.combine(start_date, time(self.vp_reset_hour, 0)))
        mask = (df_15m.index >= start_ts) & (df_15m.index <= current_time)
        session_data = df_15m.loc[mask]
        if session_data.empty: return None, None, None
        price_step = max(0.01, (session_data['High'].max() - session_data['Low'].min()) / 100)
        bins = np.arange(session_data['Low'].min(), session_data['High'].max() + price_step, price_step)
        hist, bin_edges = np.histogram(session_data['Close'], bins=bins, weights=session_data['Volume'])
        if len(hist) == 0: return None, None, None
        poc_idx = np.argmax(hist)
        poc = bin_edges[poc_idx]
        total_vol = hist.sum()
        target_vol = total_vol * self.vol_area_ratio
        current_vol = hist[poc_idx]
        low_idx = poc_idx
        high_idx = poc_idx
        while current_vol < target_vol:
            vol_below = hist[low_idx - 1] if low_idx > 0 else 0
            vol_above = hist[high_idx + 1] if high_idx < len(hist) - 1 else 0
            if vol_below == 0 and vol_above == 0: break
            if vol_below >= vol_above:
                current_vol += vol_below
                low_idx -= 1
            else:
                current_vol += vol_above
                high_idx += 1
        return bin_edges[high_idx], poc, bin_edges[low_idx]

    def calculate_day_levels(self, df_15m, df_daily, current_time):
        today = current_time.date()
        today_data = df_15m[df_15m.index.date == today]
        day_high = today_data['High'].max() if not today_data.empty else None
        day_low = today_data['Low'].min() if not today_data.empty else None
        prior_rows = df_daily[df_daily.index.date < today]
        if not prior_rows.empty:
            pdday = prior_rows.iloc[-1]
            ph, pl = pdday['High'], pdday['Low']
            if isinstance(ph, pd.Series): ph = ph.iloc[0]
            if isinstance(pl, pd.Series): pl = pl.iloc[0]
            return day_high, day_low, float(ph), float(pl)
        return day_high, day_low, None, None

    def generate_signals(self, ticker, data):
        df = data['15m'].copy()
        df_daily = data.get('daily')
        if df.empty or len(df) < 50 or df_daily is None: return []
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
        else:
            df.index = df.index.tz_convert(self.tz)
        
        signals = []
        def s(val): return float(val.iloc[0]) if isinstance(val, pd.Series) else float(val)
        session_df = df.between_time(self.window_start, self.window_end)
        
        # Group session by date to calculate VP levels once per day
        dates = pd.unique(session_df.index.date)
        daily_vp = {}
        for d in dates:
            # For each day, calculate VP levels based on data up to the start of that day's window (9:30)
            # Actually, use data up to 9:30 AM of that day.
            calc_ts = self.tz.localize(datetime.combine(d, time(9, 30)))
            vah, poc, val = self.calculate_vp_levels(df, calc_ts)
            if vah: daily_vp[d] = (vah, poc, val)

        for i in range(1, len(session_df)):
            curr_time = session_df.index[i]
            c_date = curr_time.date()
            if c_date not in daily_vp: continue
            vah, poc, val = daily_vp[c_date]
            
            curr_row = session_df.iloc[i]
            prev_row = df.loc[:curr_time].iloc[-2]
            
            c_close, c_open, c_high, c_low = s(curr_row['Close']), s(curr_row['Open']), s(curr_row['High']), s(curr_row['Low'])
            p_high, p_low = s(prev_row['High']), s(prev_row['Low'])
            
            is_manip = (c_high > p_high) and (c_low < p_low)
            if not is_manip: continue
            
            side = None
            if c_close < p_high and c_close < c_open: side = 'SHORT'
            elif c_close > p_low and c_close > c_open: side = 'LONG'
            if not side: continue
            
            vah, poc, val = self.calculate_vp_levels(df, curr_time)
            if vah is None: continue
            levels = [vah, poc, val]
            near_level = any(abs(c_close - L) / L <= self.proximity_threshold for L in levels)
            if not near_level: continue
            
            day_h, day_l, prev_h, prev_l = self.calculate_day_levels(df, df_daily, curr_time)
            if side == 'LONG':
                target = day_h if day_h else c_close * 1.01
                sl = c_low * 0.9995
                risk = c_close - sl
                reward = target - c_close
            else:
                target = day_l if day_l else c_close * 0.99
                sl = c_high * 1.0005
                risk = sl - c_close
                reward = c_close - target
                
            if risk > 0 and (reward / risk) >= self.min_rr:
                signals.append({
                    'timestamp': curr_time,
                    'ticker': ticker,
                    'type': side + '_ENTRY',
                    'entry': c_close,
                    'stop_loss': sl,
                    'tp1': target,
                    'tp2': prev_h if side == 'LONG' else prev_l
                })
        return signals

if __name__ == "__main__":
    ticker = "SPY"
    df = yf.download(ticker, period="5d", interval="15m")
    df_daily = yf.download(ticker, period="10d", interval="1d")
    strat = ManipulationReversalV4()
    sigs = strat.generate_signals(ticker, {"15m": df, "daily": df_daily})
    print(sigs)
