import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, time, timedelta
import pytz
from typing import Dict, List, Optional
import sys

class LinkPilledStrategy:
    """
    Link-Pilled Strategy: High-conviction SFP setup optimized for IBIT, LINK, SOL.
    """
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.tz = pytz.timezone('US/Eastern')
        self.cached_m5: Optional[pd.DataFrame] = None
        
    def fetch_h1_data(self, period: str = "60d") -> pd.DataFrame:
        df = yf.download(self.ticker, period=period, interval="1h", progress=False)
        if df.empty: return df
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df

    def find_clean_swing_points(self, df: pd.DataFrame, X: int = 5, Y: int = 10) -> List[Dict]:
        """Vectorized identification of clean swing points."""
        # Use simple rolling max/min for finding the pivot
        # A pivot at index 'i' means it is the max of [i-X, i+X]
        # BUT rolling window is 'centered' or 'right'.
        # rolling(window=2*X+1, center=True) at index i checks [i-X, i+X]
        # BUT rolling needs numeric index or monotonic time.
        
        # 1. Rolling Max/Min
        highs = df['High']
        lows = df['Low']
        
        # Shifted rolling ensures we don't look ahead incorrectly if we aren't careful, 
        # but center=True with closed='both' works for "at point i".
        # We need to verify if df.iloc[i] is extrema of [i-X...i+X].
        # However, lookahead bias for "detection" is allowed here because we only use it AFTER Y candles.
        
        roll_high = highs.rolling(window=2*X+1, center=True).max()
        roll_low = lows.rolling(window=2*X+1, center=True).min()
        
        is_swing_high = (highs == roll_high)
        is_swing_low = (lows == roll_low)
        
        # 2. "Clean" Check (Subsequent Y candles)
        # We need to ensure that from i+1 to i+Y, no price breaks the level.
        # We can use forward rolling window.
        # rolling(window=Y).max().shift(-Y) references future.
        # At index i, we want max of [i+1 ... i+Y].
        # Actually: indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=Y)
        # future_high_max = highs.shift(-1).rolling(window=Y).max() # This is backward if not using forward indexer
        
        # Let's use simpler shift loop for Y check or iterative approach is fast enough if N pivots is small.
        # But rolling max is fast.
        # Hacky way: reverse df, rolling, reverse back? No.
        
        # Let's stick to iterating the pivots found by rolling.
        clean_levels = []
        
        # Get indices of potential swings
        high_indices = np.where(is_swing_high)[0]
        low_indices = np.where(is_swing_low)[0]
        
        # Filter Highs
        for idx in high_indices:
            if idx < X or idx > len(df) - Y - 1: continue
            price = highs.iloc[idx]
            # Check Y future candles
            future_window = highs.iloc[idx+1 : idx+Y+1]
            if future_window.max() < price:
                clean_levels.append({'timestamp': df.index[idx], 'price': price, 'type': 'High'})
                
        # Filter Lows
        for idx in low_indices:
            if idx < X or idx > len(df) - Y - 1: continue
            price = lows.iloc[idx]
            future_window = lows.iloc[idx+1 : idx+Y+1]
            if future_window.min() > price:
                clean_levels.append({'timestamp': df.index[idx], 'price': price, 'type': 'Low'})
                
        return clean_levels

    def detect_sfp_candle(self, df: pd.DataFrame, clean_levels: List[Dict], vol_threshold: float = 1.5) -> pd.DataFrame:
        """Vectorized SFP scanning logic."""
        df = df.copy()
        df['sfp_type'] = None
        df['sfp_level'] = None
        df['vol_ma20'] = df['Volume'].rolling(window=20).mean()
        df['body_size'] = abs(df['Open'] - df['Close'])
        df['upper_wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
        df['lower_wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']
        
        # Calculate common conditions
        vol_spike = df['Volume'] > (df['vol_ma20'] * vol_threshold)
        min_body = 0.000001
        
        candidates = []
        
        for level in clean_levels:
            lvl_price = level['price']
            lvl_type = level['type']
            lvl_time = level['timestamp']
            
            # Mask for detection
            # 1. Time must be after level creation
            # 2. Price must sweep level
            # 3. Close must be inside level
            # 4. Volume spike
            # 5. Wick check
            
            mask_time = df.index > lvl_time
            
            if lvl_type == 'High':
                # Sweep High, Close < High
                mask_sweep = (df['High'] > lvl_price) & (df['Close'] < lvl_price)
                # Wick Check: upper_wick >= body * 2
                mask_wick = df['upper_wick'] >= (df['body_size'].clip(lower=min_body) * 2)
                
                final_mask = mask_time & mask_sweep & vol_spike & mask_wick
                hit_indices = df.index[final_mask]
                
                for idx in hit_indices:
                    candidates.append({
                        'idx': idx, 
                        'sfp_type': 'Short', 
                        'sfp_level': lvl_price
                    })
                    
            else:
                # Sweep Low, Close > Low
                mask_sweep = (df['Low'] < lvl_price) & (df['Close'] > lvl_price)
                mask_wick = df['lower_wick'] >= (df['body_size'].clip(lower=min_body) * 2)
                
                final_mask = mask_time & mask_sweep & vol_spike & mask_wick
                hit_indices = df.index[final_mask]
                
                for idx in hit_indices:
                    candidates.append({
                        'idx': idx, 
                        'sfp_type': 'Long', 
                        'sfp_level': lvl_price
                    })
        
        # Apply to DF
        for cand in candidates:
            # If multiple levels hit, overwrite (or handle logic? overwrite is fine for now)
            df.at[cand['idx'], 'sfp_type'] = cand['sfp_type']
            df.at[cand['idx'], 'sfp_level'] = cand['sfp_level']
            
        return df[df['sfp_type'].notnull()]

    def confirm_bos_on_LTF(self, sfp_timestamp: datetime, sfp_direction: str, df_m5: pd.DataFrame) -> Dict:
        """Fast BOS check using local M5 slice."""
        start_time = sfp_timestamp + pd.Timedelta(hours=1)
        end_time = start_time + pd.Timedelta(hours=2)
        
        m5_slice = df_m5[(df_m5.index >= sfp_timestamp - pd.Timedelta(hours=2)) & (df_m5.index <= end_time)]
        if m5_slice.empty: return {'confirmed': False}
        
        pre = m5_slice[m5_slice.index < start_time]
        post = m5_slice[m5_slice.index >= start_time]
        if pre.empty or post.empty: return {'confirmed': False}
        
        X = 3
        if sfp_direction == 'Short':
            lows = [pre.iloc[i]['Low'] for i in range(X, len(pre)-X) if pre.iloc[i]['Low'] == pre.iloc[i-X:i+X+1]['Low'].min()]
            if not lows: return {'confirmed': False}
            target = lows[-1]
            for idx, row in post.iterrows():
                if row['Close'] < target: return {'confirmed': True, 'timestamp': idx, 'level': target}
        else:
            highs = [pre.iloc[i]['High'] for i in range(X, len(pre)-X) if pre.iloc[i]['High'] == pre.iloc[i-X:i+X+1]['High'].max()]
            if not highs: return {'confirmed': False}
            target = highs[-1]
            for idx, row in post.iterrows():
                if row['Close'] > target: return {'confirmed': True, 'timestamp': idx, 'level': target}
        return {'confirmed': False}

    def run_backtest(self, vol_t: float, retrace_l: float, iso_y: int, df_h1: pd.DataFrame, df_m5: pd.DataFrame):
        """Optimized backtest with shared data."""
        levels = self.find_clean_swing_points(df_h1, Y=iso_y)
        sfps = self.detect_sfp_candle(df_h1, levels, vol_threshold=vol_t)
        
        trades = []
        for idx, row in sfps.iterrows():
            bos = self.confirm_bos_on_LTF(idx, row['sfp_type'], df_m5)
            if bos['confirmed']:
                w = row['High'] - row['Close'] if row['sfp_type'] == 'Short' else row['Close'] - row['Low']
                ent = row['High'] - (w * retrace_l) if row['sfp_type'] == 'Short' else row['Low'] + (w * retrace_l)
                sl = row['High'] + 0.10 if row['sfp_type'] == 'Short' else row['Low'] - 0.10 # IBIT 10 cent buffer
                # Simple logic: assume retrace hit if same H1 or next H1 hits it.
                # For brevity in backtest, we just assume entry for confirmed BOS
                tp = df_h1.loc[:idx].iloc[-10:]['Low'].min() if row['sfp_type'] == 'Short' else df_h1.loc[:idx].iloc[-10:]['High'].max()
                
                post = df_h1[df_h1.index > bos['timestamp']].head(24)
                for _, p in post.iterrows():
                    if row['sfp_type'] == 'Short':
                        if p['High'] >= sl: trades.append(-1); break
                        if p['Low'] <= tp: trades.append(1.5); break # 1.5R default
                    else:
                        if p['Low'] <= sl: trades.append(-1); break
                        if p['High'] >= tp: trades.append(1.5); break
        
        return sum(trades) / len(trades) if trades else 0.0

    def run_long_term_backtest(self, period: str = "2y", vol_t: float = 2.0, retrace_l: float = 0.618, iso_y: int = 5) -> Dict:
        """Hybrid Backtest: M5 confirmation for recent 60d, H1 Proxy for older history."""
        print(f"Running 2-Year Hybrid Backtest for {self.ticker}...")
        
        # 1. Fetch full H1 history
        df_h1 = self.fetch_h1_data(period=period)
        if df_h1.empty: return {'trades': 0, 'win_rate': 0.0, 'pnl': 0.0}
        
        # 2. Fetch M5 data (only gets last ~60 days)
        df_m5 = yf.download(self.ticker, period="60d", interval="5m", progress=False)
        if isinstance(df_m5.columns, pd.MultiIndex): df_m5.columns = df_m5.columns.get_level_values(0)
        
        levels = self.find_clean_swing_points(df_h1, Y=iso_y)
        sfps = self.detect_sfp_candle(df_h1, levels, vol_threshold=vol_t)
        
        trades = []
        balance = 10000
        
        # Determine Tick Size
        try:
            info = yf.Ticker(self.ticker).info
            tick_size = info.get('regularMarketPrice', 1) * 0.0001
        except: 
            tick_size = 0.01

        curr_time = pd.Timestamp.now(tz='UTC')
        
        for idx, row in sfps.iterrows():
            is_recent = (curr_time - idx).days < 58
            confirmed = False
            
            # --- CONFIRMATION LOGIC ---
            if is_recent and not df_m5.empty:
                # High Fidelity: Use M5 BOS
                bos = self.confirm_bos_on_LTF(idx, row['sfp_type'], df_m5)
                confirmed = bos['confirmed']
            else:
                # Proxy: Use H1 Structure Break (next 3 candles break range)
                # If Short SFP: Next 3 candles must close lower than SFP low? 
                # Or simplier: strict SFP is often enough, but let's require next candle to NOT engulf the SFP.
                # Proxy Rule: The next H1 candle must close in the direction of the trade (e.g. Down for Short)
                next_candle = df_h1[df_h1.index > idx].head(1)
                if not next_candle.empty:
                    nc = next_candle.iloc[0]
                    if row['sfp_type'] == 'Short' and nc['Close'] < row['Close']: confirmed = True
                    elif row['sfp_type'] == 'Long' and nc['Close'] > row['Close']: confirmed = True

            if confirmed:
                # --- EXECUTION LOGIC ---
                w = row['High'] - row['Close'] if row['sfp_type'] == 'Short' else row['Close'] - row['Low']
                ent = row['High'] - (w * retrace_l) if row['sfp_type'] == 'Short' else row['Low'] + (w * retrace_l)
                sl = row['High'] + (10 * tick_size) if row['sfp_type'] == 'Short' else row['Low'] - (10 * tick_size)
                
                # Dynamic TP: Use recent H1 extremes
                lookback = df_h1.loc[:idx].iloc[-24:] # 1 day lookback
                tp = lookback['Low'].min() if row['sfp_type'] == 'Short' else lookback['High'].max()
                
                # Risk 1%
                risk_amt = balance * 0.01
                dist = abs(ent - sl)
                if dist == 0: continue
                size = risk_amt / dist
                
                # Simulate Outcome
                post_data = df_h1[df_h1.index > idx].head(48) # 48h limit
                outcome_pnl = 0
                
                for _, p in post_data.iterrows():
                    if row['sfp_type'] == 'Short':
                        if p['High'] >= sl: outcome_pnl = -risk_amt; break
                        if p['Low'] <= tp: outcome_pnl = (ent - tp) * size; break
                    else:
                        if p['Low'] <= sl: outcome_pnl = -risk_amt; break
                        if p['High'] >= tp: outcome_pnl = (tp - ent) * size; break
                        
                if outcome_pnl != 0:
                    balance += outcome_pnl
                    trades.append({'time': idx, 'pnl': outcome_pnl, 'balance': balance})
        
        win_rate = (len([t for t in trades if t['pnl'] > 0]) / len(trades) * 100) if trades else 0
        total_pnl = balance - 10000
        
        return {
            'symbol': self.ticker,
            'trades': len(trades),
            'win_rate': win_rate,
            'pnl': total_pnl,
            'roi': (total_pnl / 10000) * 100
        }

    def run_optimization(self):
        print("Starting Hyperparameter Optimization...")
        df_h1 = self.fetch_h1_data(period="60d")
        df_m5 = yf.download(self.ticker, period="60d", interval="5m", progress=False)
        if isinstance(df_m5.columns, pd.MultiIndex): df_m5.columns = df_m5.columns.get_level_values(0)

        results = []
        for v in [1.2, 1.5, 2.0]:
            for r in [0.382, 0.5, 0.618]:
                for y in [5, 10, 15]:
                    score = self.run_backtest(v, r, y, df_h1, df_m5)
                    results.append({'vol': v, 'retrace': r, 'iso': y, 'metric': score})
                    print(f"V:{v} R:{r} Y:{y} -> Score: {score:.4f}")
        
        df_res = pd.DataFrame(results)
        best = df_res.sort_values('metric', ascending=False).iloc[0]
        print(f"\n--- Best Parameters ---\n{best}")
        
        # Heatmap plot: vol vs retrace (iso averaged)
        pivot = df_res.pivot_table(index='vol', columns='retrace', values='metric', aggfunc='mean')
        v_list = [1.2, 1.5, 2.0]
        r_list = [0.382, 0.5, 0.618]
        plt.figure(figsize=(8, 6))
        plt.imshow(pivot, cmap='Greys', interpolation='nearest')
        plt.colorbar(label='Avg Metric')
        plt.xticks(range(len(r_list)), r_list)
        plt.yticks(range(len(v_list)), v_list)
        plt.title("SFP Optimization Heatmap (Sharpe Proxy)")
        plt.xlabel("Retracement Level")
        plt.ylabel("Volume Threshold")
        plt.savefig("optimization_heatmap.png")
        plt.close()

if __name__ == "__main__":
    import sys
    tickers = ["IBIT", "CLNK", "ETHE", "IREN"]
    results = []
    
    if "--optimize" in sys.argv:
        strategy = LinkPilledStrategy("IBIT")
        strategy.run_optimization()
    else:
        for ticker in tickers:
            print(f"\n{'='*20} TESTING {ticker} {'='*20}")
            strategy = LinkPilledStrategy(ticker)
            res = strategy.run_long_term_backtest(period="2y")
            results.append(res)
        
        print("\n" + "="*50)
        print("LINK-PILLED BULK RESULTS")
        print("="*50)
        for r in results:
            print(f"{r['symbol']}: WR: {r['win_rate']:.2f}% | ROI: {r['roi']:.2f}% | Trades: {r['trades']}")
