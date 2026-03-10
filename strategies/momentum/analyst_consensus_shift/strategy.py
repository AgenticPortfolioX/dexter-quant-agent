import os
import sys
import sqlite3
import re
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Add project roots to path
project_root = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
momentum_root = os.path.join(project_root, "strategies", "momentum")
if momentum_root not in sys.path:
    sys.path.append(momentum_root)

# Gatekeeper import
try:
    from value_trap_filter.strategy import ValueTrapFilter
except ImportError:
    ValueTrapFilter = None

class AnalystConsensusStrategy:
    """
    Momentum Strategy 6: Analyst Consensus Shift (Institutional)
    Targets stocks with a 7-day 'Cluster' of upgrades and PT hikes.
    """
    def __init__(self, api_key: str = None, db_path: str = "analyst_signals.db"):
        self.api_key = api_key
        self.db_path = db_path
        self.gatekeeper = ValueTrapFilter() if ValueTrapFilter else None
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analyst_clusters (
                ticker TEXT,
                upgrade_count_7d INTEGER,
                avg_pt REAL,
                upside_pct REAL,
                date TEXT,
                status TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def fetch_ratings(self, days_back: int = 7) -> List[Dict]:
        """
        Mock for TipRanks/Benzinga ratings feed.
        """
        if not self.api_key: return []
        # Implementation would call Apify or Benzinga endpoint
        return []

    def normalize_firm_name(self, name: str) -> str:
        """
        Deduplicates firm names using simple keyword matching.
        """
        name = name.upper().strip()
        if "GOLDMAN SACHS" in name: return "GOLDMAN SACHS"
        if "MORGAN STANLEY" in name: return "MORGAN STANLEY"
        if "JP MORGAN" in name or "JPMORGAN" in name: return "JPMORGAN"
        if "BANK OF AMERICA" in name or "BOFA" in name or "MERRILL" in name: return "BOFA"
        if "WELLS FARGO" in name: return "WELLS FARGO"
        if "CITIGROUP" in name or "CITI " in name: return "CITI"
        return name

    def filter_clusters(self, ratings: List[Dict]) -> Dict[str, Dict]:
        """
        Groups ratings by ticker and identifies clusters (>= 3 distinct firms).
        """
        if not ratings: return {}
        
        df = pd.DataFrame(ratings)
        df['normalized_firm'] = df['firm'].apply(self.normalize_firm_name)
        
        # Valid actions: Upgrade, Initiated, Price Target Raise
        valid_actions = ['UPGRADE', 'INITIATED', 'RAISE', 'POSITIVE', 'BUY']
        df = df[df['action'].str.upper().str.contains('|'.join(valid_actions))]
        
        clusters = {}
        grouped = df.groupby('ticker')
        
        for ticker, group in grouped:
            unique_firms = group['normalized_firm'].nunique()
            if unique_firms >= 3:
                # Exclude speculative keywords
                speculative = False
                for reason in group.get('reasoning', []):
                    if re.search(r"speculative|M&A rumors|takeover", str(reason), re.IGNORECASE):
                        speculative = True
                        break
                
                if not speculative:
                    avg_pt = group['price_target'].mean() if 'price_target' in group.columns else 0
                    clusters[ticker] = {
                        'count': unique_firms,
                        'avg_pt': avg_pt
                    }
                    
        return clusters

    def check_divergence_and_upside(self, ticker: str, avg_pt: float) -> Optional[Dict]:
        """
        Upside > 15% and 5-day price change < 2%.
        """
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="10d")
            if len(hist) < 6: return None
            
            current_price = hist['Close'].iloc[-1]
            five_days_ago = hist['Close'].iloc[-6]
            
            five_day_change = (current_price / five_days_ago - 1) * 100
            upside_pct = (avg_pt / current_price - 1) * 100
            
            # Divergence logic:institutional shift without retail FOMO yet
            if upside_pct > 15.0 and five_day_change < 2.0:
                return {
                    'current_price': current_price,
                    'upside_pct': upside_pct,
                    'divergence': five_day_change
                }
        except:
            pass
        return None

    def run_daily_scan(self):
        print(f"--- ANALYST CONSENSUS SHIFT SCAN: {datetime.now().strftime('%Y-%m-%d')} ---")
        ratings = self.fetch_ratings()
        clusters = self.filter_clusters(ratings)
        
        for ticker, data in clusters.items():
            # 1. Price Target and Divergence Check
            metrics = self.check_divergence_and_upside(ticker, data['avg_pt'])
            if metrics:
                # 2. Gatekeeper Check (Value Trap Filter)
                if self.gatekeeper and not self.gatekeeper.validate_quality(ticker):
                    print(f"[GATEKEEPER] {ticker} disqualified as Value Trap.")
                    continue
                
                # 3. Store Signal
                self._store_signal(ticker, data['count'], data['avg_pt'], metrics['upside_pct'])
                print(f"[SIGNAL] {ticker} Institutional Cluster: {data['count']} firms | Upside: {metrics['upside_pct']:.2f}%")

    def _store_signal(self, ticker: str, count: int, avg_pt: float, upside: float):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO analyst_clusters (ticker, upgrade_count_7d, avg_pt, upside_pct, date, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ticker, count, avg_pt, upside, datetime.now().strftime("%Y-%m-%d"), 'active'))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    strat = AnalystConsensusStrategy()
    print("Analyst Consensus Shift Strategy Structured.")
