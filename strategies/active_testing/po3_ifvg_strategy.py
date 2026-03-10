import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, time, timedelta
import pytz
from typing import Dict, List, Optional, Tuple

class PO3IFVGStrategy:
    """
    Optimized Power of Three (PO3) + Inversion Fair Value Gap (IFVG) Strategy.
    RELAXED PARAMETERS for higher signal frequency.
    """
    def __init__(self, ticker: str = "QQQ"):
        self.ticker = ticker
        self.tz = pytz.timezone('America/New_York')
        self.session_start = "09:30"
        # EXPANDED PARAMETERS
        self.mani_threshold = 1.0 # Reduced from 1.5x ATR
        self.acc_duration_hrs = 1.5 # Increased from 1.0h
        self.mani_window_hrs = 3.5 # Increased from 2.5h
        self.fvg_lookback = 10 # Increased from 5 candles
        self.cached_htf_df = None # HTF Cache

    def fetch_data(self, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
        try:
            df = yf.download(self.ticker, period=period, interval=interval, progress=False)
            if df.empty: return df
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert(self.tz)
            else:
                df.index = df.index.tz_convert(self.tz)
            return df
        except Exception as e:
            print(f"Fetch Error: {e}")
            return pd.DataFrame()

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        return true_range.rolling(period).mean()

    def get_htf_bias(self, ticker: str, time_point: datetime) -> str:
        try:
            # CHECK CACHE FIRST
            if self.cached_htf_df is not None and not self.cached_htf_df.empty:
                df_h = self.cached_htf_df
            else:
                df_h = yf.download(ticker, period="60d", interval="1h", progress=False)
                if df_h.empty: return "Neutral"
                if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                if df_h.index.tz is None:
                    df_h.index = df_h.index.tz_localize('UTC').tz_convert(self.tz)
                else:
                    df_h.index = df_h.index.tz_convert(self.tz)
                self.cached_htf_df = df_h # POPULATE CACHE
            
            # Use cached or newly downloaded data
            df_slice = df_h[df_h.index <= time_point]
            if len(df_slice) < 20: return "Neutral"
            ema20 = df_slice['Close'].ewm(span=20, adjust=False).mean()
            current_close = df_slice['Close'].iloc[-1]
            current_ema = ema20.iloc[-1]
            return "Bullish" if current_close > current_ema else "Bearish"
        except:
            return "Neutral"

    def clear_cache(self):
        self.cached_htf_df = None

    def detect_po3_phases(self, day_data: pd.DataFrame, session_start: str = "09:30") -> Dict:
        results = {"accumulation_range": None, "manipulation_swipe": None, "base_atr": 0.0}
        try:
            start_dt = datetime.strptime(session_start, "%H:%M").time()
            acc_end_dt = (datetime.combine(datetime.today(), start_dt) + timedelta(hours=self.acc_duration_hrs)).time()
            acc_phase = day_data.between_time(session_start, acc_end_dt.strftime("%H:%M"))
            if acc_phase.empty: return results
            acc_high = acc_phase['High'].max()
            acc_low = acc_phase['Low'].min()
            results["accumulation_range"] = (float(acc_low), float(acc_high))
            day_data = day_data.copy()
            day_data['atr'] = self.calculate_atr(day_data)
            base_atr = day_data.loc[acc_phase.index].iloc[-1]['atr']
            results["base_atr"] = float(base_atr)
            mani_start_dt = acc_end_dt
            mani_end_dt = (datetime.combine(datetime.today(), start_dt) + timedelta(hours=self.mani_window_hrs)).time()
            mani_window = day_data.between_time(mani_start_dt.strftime("%H:%M"), mani_end_dt.strftime("%H:%M"))
            if mani_window.empty: return results
            for t, row in mani_window.iterrows():
                move_up = row['High'] - acc_high
                move_down = acc_low - row['Low']
                if move_up > (base_atr * self.mani_threshold):
                    results["manipulation_swipe"] = ("UP", float(row['High']), t)
                    break
                if move_down > (base_atr * self.mani_threshold):
                    results["manipulation_swipe"] = ("DOWN", float(row['Low']), t)
                    break
        except Exception as e:
            print(f"PO3 Error: {e}")
        return results

    def find_fvgs(self, df: pd.DataFrame, start_time: datetime, end_time: datetime) -> List[Dict]:
        fvgs = []
        window_df = df[(df.index >= start_time) & (df.index <= end_time)]
        if len(window_df) < 3: return fvgs
        for i in range(1, len(window_df) - 1):
            c1 = window_df.iloc[i-1]
            c3 = window_df.iloc[i+1]
            if c1['High'] < c3['Low']:
                fvgs.append({"type": "BULLISH", "top": float(c3['Low']), "bottom": float(c1['High']), "time": window_df.index[i]})
            elif c1['Low'] > c3['High']:
                fvgs.append({"type": "BEARISH", "top": float(c1['Low']), "bottom": float(c3['High']), "time": window_df.index[i]})
        return fvgs

    def generate_signals(self, df: pd.DataFrame, use_htf_filter: bool = False) -> List[Dict]:
        signals = []
        if df.empty: return signals
        days = df.groupby(df.index.date)
        for date, day_data in days:
            if len(day_data) < 20: continue
            po3 = self.detect_po3_phases(day_data, self.session_start)
            if not po3["manipulation_swipe"]: continue
            mani_type, mani_price, mani_time = po3["manipulation_swipe"]
            try:
                mani_idx = day_data.index.get_loc(mani_time)
                if isinstance(mani_idx, slice): mani_idx = mani_idx.start
                elif isinstance(mani_idx, np.ndarray): mani_idx = np.where(mani_idx)[0][0]
            except:
                mani_idx = np.searchsorted(day_data.index, mani_time)
            lookback_start = day_data.index[max(0, mani_idx - self.fvg_lookback)]
            fvgs = self.find_fvgs(day_data, lookback_start, mani_time)
            if not fvgs: continue
            target_fvg = fvgs[-1]
            if use_htf_filter:
                bias = self.get_htf_bias(self.ticker, mani_time)
                if (mani_type == "DOWN" and bias != "Bullish") or (mani_type == "UP" and bias != "Bearish"):
                    continue
            post_mani = day_data[day_data.index > mani_time].head(30) # Increased monitor window
            for t, row in post_mani.iterrows():
                entry_found, side = False, None
                if target_fvg['type'] == "BEARISH" and mani_type == "DOWN":
                    if row['Close'] > target_fvg['top']: entry_found, side = True, "Long"
                elif target_fvg['type'] == "BULLISH" and mani_type == "UP":
                    if row['Close'] < target_fvg['bottom']: entry_found, side = True, "Short"
                if entry_found:
                    entry_price, sl = float(row['Close']), float(mani_price)
                    r = abs(entry_price - sl)
                    if r == 0: continue
                    signals.append({
                        'date': date, 'time': t, 'side': side, 'entry': entry_price, 'sl': sl,
                        'tp1': entry_price + (1.2 * r) if side == "Long" else entry_price - (1.2 * r), # Relaxed TP
                        'tp2': entry_price + (2.5 * r) if side == "Long" else entry_price - (2.5 * r)  # Expanded TP
                    })
                    break
        return signals

if __name__ == "__main__":
    strat = PO3IFVGStrategy()
    data = strat.fetch_data(period="1mo")
    sigs = strat.generate_signals(data)
    print(f"Signals Found: {len(sigs)}")
