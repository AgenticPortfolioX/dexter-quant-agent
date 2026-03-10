import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import zscore
from datetime import datetime
import os

class EquityMRStrategy:
    """
    Systematic Intraday-Rebalanced Equity Mean-Reversion Strategy.
    Scope: Strategy Creation Only.
    Logic: Residual mean reversion after orthogonalizing to Market, Size, Value, Momentum, and Sector.
    """
    def __init__(self, target_vol=0.10):
        self.target_vol = target_vol
        self.lookback_beta = 63
        self.lookback_vol = 252
        self.horizons = [1, 3, 5]
        self.weights = {1: 0.50, 3: 0.30, 5: 0.20}
        
    def get_factor_data(self, start_date, end_date):
        """
        Fetches synthetic factor proxies.
        """
        proxies = {
            'MKT': 'SPY',
            'SIZE': 'IWM',
            'VALUE': 'IVE',
            'GROWTH': 'IVW',
            'MOM': 'MTUM'
        }
        factors = pd.DataFrame()
        for name, ticker in proxies.items():
            df = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            factors[name] = np.log(df['Close'] / df['Close'].shift(1))
            
        factors['VAL_PROXY'] = factors['VALUE'] - factors['GROWTH']
        factors = factors[['MKT', 'SIZE', 'VAL_PROXY', 'MOM']].dropna()
        return factors

    def calculate_residuals(self, stock_rets, factors):
        """
        Orthogonalize stock returns to factors to get idiosyncratic residuals.
        """
        common_idx = stock_rets.index.intersection(factors.index)
        if len(common_idx) < self.lookback_beta:
            return None
            
        y = stock_rets.loc[common_idx].values
        X = factors.loc[common_idx].values
        X = np.column_stack([np.ones(len(X)), X]) # Add Intercept
        
        # OLS: y = Xb + e -> b = (X'X)^-1 X'y
        if len(X) < self.lookback_beta:
            return None
            
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ beta
        residuals = y - pred
        return pd.Series(residuals, index=common_idx)

    def get_ensemble_signal(self, universe_data, factors):
        """
        Standardize and ensemble residuals over multiple horizons.
        """
        all_signals = {}
        for ticker, df in universe_data.items():
            if len(df) < 200: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
            stock_rets = np.log(df['Close'] / df['Close'].shift(1)).dropna()
            residuals = self.calculate_residuals(stock_rets, factors)
            
            if residuals is None or len(residuals) < 5: continue
            
            # Combine Z-scores for 1, 3, 5 days
            z_sum = 0
            for k in self.horizons:
                res_k = residuals.tail(k).mean()
                z_k = (res_k - residuals.mean()) / residuals.std() if residuals.std() > 0 else 0
                z_sum += self.weights[k] * z_k
            
            all_signals[ticker] = -z_sum # Negative for Mean Reversion
            
        return pd.Series(all_signals)

    def get_signal(self, signals, ticker):
        """
        Identify entry/exit based on signal strength.
        """
        if ticker not in signals.index:
            return "NONE", 0
            
        s = signals[ticker]
        if s > 1.5:
            return "BUY", s
        elif s < -1.5:
            return "SELL", s
        elif abs(s) < 0.5:
            return "EXIT", s
            
        return "NONE", s

if __name__ == "__main__":
    # Local Logic Test
    tickers = ["AAPL", "MSFT", "NVDA", "JPM", "XOM"]
    print(f"Testing Equity MR Logic for {len(tickers)} tickers...")
    
    strat = EquityMRStrategy()
    
    # Setup data
    universe = {}
    for t in tickers:
        universe[t] = yf.download(t, period="1y", progress=False)
        
    factors = strat.get_factor_data("2023-01-01", datetime.now().strftime("%Y-%m-%d"))
    
    signals = strat.get_ensemble_signal(universe, factors)
    
    print("\n--- Equity MR Signals (Residual Reversion) ---")
    for t, s in signals.items():
        sig_type, strength = strat.get_signal(signals, t)
        print(f"Ticker: {t:5} | Signal: {s:8.2f} | Action: {sig_type}")
