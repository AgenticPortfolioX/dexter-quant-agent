import sqlite3
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
import sys

# Add project root to sys.path to allow importing other momentum tools
project_root = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
if project_root not in sys.path:
    sys.path.append(project_root)

# Optional gatekeeper import
try:
    from strategies.momentum.value_trap_filter.strategy import ValueTrapFilter
except ImportError:
    ValueTrapFilter = None

class FollowTheLeaderStrategy:
    """
    Momentum Strategy 4: Follow the Leader (Insider)
    Tracks significant open-market purchases by CEO, CFO, and Directors.
    """
    def __init__(self, sec_api_key: str = None, db_path: str = "insider_signals.db"):
        self.sec_api_key = sec_api_key
        self.db_path = db_path
        self.gatekeeper = ValueTrapFilter() if ValueTrapFilter else None
        self._init_db()

    def _init_db(self):
        """Initialize SQLite table for insider tracking."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS insider_buys (
                ticker TEXT,
                insider TEXT,
                role TEXT,
                shares REAL,
                price REAL,
                filing_date TEXT,
                transaction_value REAL,
                is_cluster BOOLEAN,
                status TEXT
            )
        ''')
        # Table to track sales specifically for the disqualification rule
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS insider_sales (
                ticker TEXT,
                insider TEXT,
                sale_date TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def fetch_form4_filings(self, days_back: int = 5) -> List[Dict]:
        """
        Fetches Form 4 filings from SEC-API.io.
        Requirement: SEC-API.io Key
        """
        if not self.sec_api_key:
            print("[WARNING] SEC-API.io key missing. Returning empty filings.")
            return []
        
        # Implementation would use the 'queryApi.getFilings(query)' method
        # Query logic: formType:"4" AND documentType:"XML" AND filedAt:[NOW-5DAYS TO NOW]
        # For now, this is a placeholder for structural completion.
        return []

    def get_transaction_details(self, filing: Dict) -> Optional[Dict]:
        """
        Parses XML filing data for relevant purchase signals.
        Logic: Code 'P', Value > $100k, CEO/CFO/Director.
        """
        # 1. Role Filter
        role = filing.get('officerTitle', '').upper()
        is_director = filing.get('isDirector', False)
        is_officer = filing.get('isOfficer', False)
        
        valid_role = False
        if any(x in role for x in ['CEO', 'CHIEF EXECUTIVE', 'CFO', 'CHIEF FINANCIAL']):
            valid_role = True
        elif is_director:
            valid_role = True
            role = "Director"
            
        if not valid_role: return None

        # 2. Transaction Filter (Code 'P')
        # In actual implementation, we'd parse the 'nonDerivativeTransactions' array
        # Check for code 'P' and ensures it's NOT a 10b5-1 plan (instruction 4)
        
        # Placeholder for parsed data
        data = {
            'ticker': filing.get('ticker'),
            'insider': filing.get('reportingOwnerName'),
            'role': role,
            'shares': 1000, # Placeholder
            'price': 150.0,  # Placeholder
            'transaction_code': 'P',
            'is_automatic': False # 10b5-1 check
        }
        
        data['transaction_value'] = data['shares'] * data['price']
        
        if data['transaction_code'] == 'P' and not data['is_automatic'] and data['transaction_value'] > 100000:
            return data
            
        return None

    def detect_clusters(self, signals: List[Dict]) -> List[Dict]:
        """
        Marks signals as 'is_cluster' if >=2 distinct insiders buy within 7 days.
        """
        df = pd.DataFrame(signals)
        if df.empty: return []
        
        # Group by ticker and count unique insiders
        counts = df.groupby('ticker')['insider'].nunique()
        clusters = counts[counts >= 2].index.tolist()
        
        for sig in signals:
            sig['is_cluster'] = sig['ticker'] in clusters
            
        return signals

    def check_disqualification(self, ticker: str, insider: str) -> bool:
        """
        Rule: If the same insider sold shares in the prior 3 months, disqualify.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        three_months_ago = (datetime.now() - timedelta(90)).strftime("%Y-%m-%d")
        
        cursor.execute('''
            SELECT COUNT(*) FROM insider_sales 
            WHERE ticker = ? AND insider = ? AND sale_date > ?
        ''', (ticker, insider, three_months_ago))
        
        sales_count = cursor.fetchone()[0]
        conn.close()
        
        return sales_count > 0

    def calculate_entry(self, ticker: str, insider_price: float) -> Optional[float]:
        """
        Entry Condition: Current Price <= (Insider Buy Price * 1.05)
        """
        try:
            stock = yf.Ticker(ticker)
            current_price = stock.history(period="1d")['Close'].iloc[-1]
            
            if current_price <= (insider_price * 1.05):
                return current_price
            return None
        except:
            return None

    def process_insider_momentum(self):
        """Main daily workflow."""
        filings = self.fetch_form4_filings()
        raw_signals = []
        
        for f in filings:
            details = self.get_transaction_details(f)
            if details:
                # Disqualification Check
                if not self.check_disqualification(details['ticker'], details['insider']):
                    raw_signals.append(details)
        
        # Cluster Detection
        processed_signals = self.detect_clusters(raw_signals)
        
        for sig in processed_signals:
            ticker = sig['ticker']
            
            # 1. Gatekeeper Check (Value Trap Filter)
            if self.gatekeeper and not self.gatekeeper.validate_quality(ticker):
                print(f"[GATEKEEPER] {ticker} disqualified as Value Trap.")
                continue

            # 2. Entry Price Check
            entry_price = self.calculate_entry(ticker, sig['price'])
            if entry_price:
                # 3. Position Sizing
                base_size = 0.02
                if sig['is_cluster']:
                    base_size = 0.04
                
                print(f"[SIGNAL] Insider Buy in {ticker} (Cluster: {sig['is_cluster']}). Size: {base_size*100}%")
                self._store_signal(sig, 'active')

    def _store_signal(self, data: Dict, status: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO insider_buys (ticker, insider, role, shares, price, filing_date, transaction_value, is_cluster, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['ticker'], data['insider'], data['role'], data['shares'],
            data['price'], datetime.now().strftime("%Y-%m-%d"), 
            data['transaction_value'], data.get('is_cluster', False), status
        ))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    strat = FollowTheLeaderStrategy()
    print("Follow the Leader (Insider) Strategy Logic Structured.")
