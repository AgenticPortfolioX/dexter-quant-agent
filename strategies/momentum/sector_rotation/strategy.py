import sqlite3
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class SectorRotationStrategy:
    """
    Momentum Strategy 2: Sector Rotation (Narrative)
    Uses 20-day ROC for ranking and 1-month correlation for diversification.
    """
    def __init__(self, db_path: str = "sector_rankings.db"):
        self.db_path = db_path
        self.sectors = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
        self.benchmark = "SPY"
        self._init_db()

    def _init_db(self):
        """Initialize SQLite table for tracking sector rankings."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sector_rankings (
                date TEXT,
                sector TEXT,
                roc_20d REAL,
                rank INTEGER,
                holding_weight REAL,
                status TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def fetch_data(self) -> Dict[str, pd.Series]:
        """Fetch 250 days of adjusted close data for ETFs and SPY."""
        tickers = self.sectors + [self.benchmark]
        data = yf.download(tickers, period="1y", interval="1d", progress=False)['Adj Close']
        return data

    def calculate_momentum_and_rank(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculates 20-day ROC and ranks sectors."""
        # 20-day ROC: (today / 20_days_ago - 1) * 100
        roc = ((data[self.sectors].iloc[-1] / data[self.sectors].iloc[-21]) - 1) * 100
        rankings = roc.sort_values(ascending=False).to_frame(name='roc_20d')
        rankings['rank'] = range(1, len(rankings) + 1)
        return rankings

    def get_market_filter(self, data: pd.DataFrame) -> bool:
        """Checks if SPY is above its 200-day SMA."""
        spy_200_sma = data[self.benchmark].rolling(200).mean().iloc[-1]
        spy_price = data[self.benchmark].iloc[-1]
        return spy_price > spy_200_sma

    def select_top_diversified_sectors(self, data: pd.DataFrame, rankings: pd.DataFrame) -> List[str]:
        """
        Selects top 2 sectors ensuring correlation between them is <= 0.85.
        Uses 21-day returns for correlation calculation.
        """
        # Calculate daily returns for the last 21 days
        returns = data[self.sectors].tail(22).pct_change().dropna()
        corr_matrix = returns.corr()
        
        top_candidates = rankings.index.tolist()
        selection = [top_candidates[0]] # Always take #1 if eligible
        
        for i in range(1, len(top_candidates)):
            candidate = top_candidates[i]
            # Check correlation with already selected
            is_diversified = True
            for selected in selection:
                if corr_matrix.loc[candidate, selected] > 0.85:
                    is_diversified = False
                    break
            
            if is_diversified:
                selection.append(candidate)
            
            if len(selection) == 2:
                break
                
        return selection

    def rebalance(self):
        """Monthly rebalance workflow."""
        data = self.fetch_data()
        if data.empty: return
        
        # 1. Market Filter (SPY > 200 SMA)
        if not self.get_market_filter(data):
            print("[INFO] SPY below 200 SMA. Staying in Cash.")
            self._log_portfolio(pd.DataFrame(), "CASH_FILTER")
            return

        # 2. Ranking
        rankings = self.calculate_momentum_and_rank(data)
        
        # 3. Selection with Correlation Check
        selection = self.select_top_diversified_sectors(data, rankings)
        
        # 4. SMA Check for individual sectors
        final_selection = []
        for s in selection:
            s_200_sma = data[s].rolling(200).mean().iloc[-1]
            if data[s].iloc[-1] > s_200_sma:
                final_selection.append(s)
            else:
                print(f"[INFO] Skipping {s}, price below its 200 SMA.")

        # 5. Log and Output
        self._log_portfolio(rankings, "INDEXED", final_selection)

    def _log_portfolio(self, rankings: pd.DataFrame, status: str, selected: List[str] = None):
        """Logs the rebalance results to SQLite."""
        conn = sqlite3.connect(self.db_path)
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # If cash, log empty
        if selected is None:
            conn.execute("INSERT INTO sector_rankings (date, sector, status) VALUES (?, ?, ?)", (date_str, "CASH", status))
        else:
            for sector in rankings.index:
                weight = 0.5 if sector in selected else 0.0
                conn.execute('''
                    INSERT INTO sector_rankings (date, sector, roc_20d, rank, holding_weight, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (date_str, sector, rankings.loc[sector, 'roc_20d'], int(rankings.loc[sector, 'rank']), weight, status))
        
        conn.commit()
        conn.close()
        if selected:
            print(f"[MONTHLY REBALANCE] Positions: {selected}")

if __name__ == "__main__":
    strat = SectorRotationStrategy()
    print("Sector Rotation Strategy Logic Structured.")
    # strat.rebalance() # For manual test
