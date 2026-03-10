import os
import sys
import json
import sqlite3
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Add project root and momentum root to sys.path
project_root = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
momentum_root = os.path.join(project_root, "strategies", "momentum")
for path in [project_root, momentum_root]:
    if path not in sys.path:
        sys.path.append(path)

# Gatekeeper import
try:
    from value_trap_filter.strategy import ValueTrapFilter
except ImportError:
    ValueTrapFilter = None

class SupplyChainRippleStrategy:
    """
    Momentum Strategy 5: Supply Chain Ripple (Second‑Order)
    Captures drift in customer stocks following blowout supplier earnings.
    """
    def __init__(self, finnhub_key: str = None, db_path: str = "ripple_signals.db"):
        self.finnhub_key = finnhub_key
        self.db_path = db_path
        self.map_path = os.path.join(os.path.dirname(__file__), "supply_chain_map.json")
        self.gatekeeper = ValueTrapFilter() if ValueTrapFilter else None
        self._init_db()

    def _init_db(self):
        """Initialize SQLite table for tracking ripple signals."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ripple_signals (
                ticker TEXT,
                supplier TEXT,
                entry_date TEXT,
                exit_date TEXT,
                status TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def load_supply_chain_map(self) -> Dict[str, List[str]]:
        if not os.path.exists(self.map_path): return {}
        with open(self.map_path, 'r') as f:
            return json.load(f)

    def fetch_supplier_earnings(self, date: str) -> List[Dict]:
        """
        Mock/Placeholder for Finnhub earnings calendar.
        Requires Finnhub key for production use.
        """
        if not self.finnhub_key: return []
        # Implementation would call Finnhub /calendar/earnings endpoint
        return []

    def check_correlation(self, ticker1: str, ticker2: str) -> float:
        """
        Computes 1-year daily return correlation between supplier and customer.
        Target: > 0.5
        """
        try:
            data = yf.download([ticker1, ticker2], period="1y", interval="1d", progress=False)['Adj Close']
            returns = data.pct_change().dropna()
            return returns[ticker1].corr(returns[ticker2])
        except:
            return 0.0

    def get_inventory_status(self, supplier_ticker: str) -> bool:
        """
        Rule: Inventory growth > Revenue growth + 10% = Disqualify.
        """
        try:
            stock = yf.Ticker(supplier_ticker)
            financials = stock.financials
            balance_sheet = stock.balance_sheet
            
            if 'Inventory' not in balance_sheet.index or 'Total Revenue' not in financials.index:
                return True # Pass if data missing to avoid false negatives
                
            rev_growth = (financials.loc['Total Revenue'].iloc[0] / financials.loc['Total Revenue'].iloc[1]) - 1
            inv_growth = (balance_sheet.loc['Inventory'].iloc[0] / balance_sheet.loc['Inventory'].iloc[1]) - 1
            
            if inv_growth > (rev_growth + 0.10):
                return False # Disqualified: Potential channel stuffing
            return True
        except:
            return True

    def get_customer_earnings_date(self, customer_ticker: str) -> Optional[datetime]:
        """
        Fetches next earnings date. Required for 2-4 week window check.
        """
        try:
            stock = yf.Ticker(customer_ticker)
            calendar = stock.calendar
            if calendar is not None and not calendar.empty:
                # The calendar object in yfinance is inconsistent, but often contains 'Earnings Date'
                # For production, Finnhub confirmed dates are preferred.
                date = calendar.iloc[0, 0] 
                if isinstance(date, datetime): return date
        except:
            pass
        return None

    def run_daily_scan(self):
        print(f"--- SUPPLY CHAIN RIPPLE SCAN: {datetime.now().strftime('%Y-%m-%d')} ---")
        supply_map = self.load_supply_chain_map()
        yesterday = (datetime.now() - timedelta(1)).strftime("%Y-%m-%d")
        
        # 1. Fetch Today's reports (Suppliers)
        suppliers_reporting = self.fetch_supplier_earnings(yesterday)
        
        for rep in suppliers_reporting:
            supplier = rep['symbol']
            rev_surprise = rep.get('revenueSurprisePct', 0)
            
            if supplier in supply_map and rev_surprise > 5.0:
                print(f"[CATALYST] Supplier {supplier} reported surprise of {rev_surprise}%")
                
                # Check Inventory Safety
                if not self.get_inventory_status(supplier):
                    print(f"[REJECTED] {supplier} failed Inventory growth check.")
                    continue
                
                customers = supply_map[supplier]
                for customer in customers:
                    # 2. Correlation Check
                    corr = self.check_correlation(supplier, customer)
                    if corr < 0.5:
                        print(f"[SKIPPED] {customer} correlation with {supplier} too low ({corr:.2f})")
                        continue
                    
                    # 3. Earnings Window Check (2-4 weeks)
                    earn_date = self.get_customer_earnings_date(customer)
                    if not earn_date: continue
                    
                    time_to_earn = (earn_date.date() - datetime.now().date()).days
                    if 14 <= time_to_earn <= 28:
                        # 4. Gatekeeper Check (Value Trap)
                        if self.gatekeeper and not self.gatekeeper.validate_quality(customer):
                            print(f"[GATEKEEPER] {customer} disqualified as Value Trap.")
                            continue
                        
                        # 5. Price Check (Not already up 10%)
                        # Implementation would check price drift since supplier report
                        
                        self._store_signal(customer, supplier, earn_date)
                        print(f"[SIGNAL] Buying {customer} due to {supplier} ripple. Exit before {earn_date}")

    def _store_signal(self, customer: str, supplier: str, earn_date: datetime):
        conn = sqlite3.connect(self.db_path)
        exit_date = (earn_date - timedelta(2)).strftime("%Y-%m-%d")
        conn.execute('''
            INSERT INTO ripple_signals (ticker, supplier, entry_date, exit_date, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (customer, supplier, datetime.now().strftime("%Y-%m-%d"), exit_date, 'active'))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    strat = SupplyChainRippleStrategy()
    print("Supply Chain Ripple Strategy Structured.")
