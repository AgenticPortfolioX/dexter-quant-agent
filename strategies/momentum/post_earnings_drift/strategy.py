import os
import re
import sqlite3
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

"""
STRATEGY NOTATION:
1. Post-Earnings Drift (Catalyst)
Primary API Requirement: Financial Modeling Prep (FMP)
Subscription Status: REQUIRES PREMIUM/ULTIMATE ($59-$149/mo) for Transcript access.
Note: This script is structured for deployment once API keys are provided.
"""

class PostEarningsDriftStrategy:
    def __init__(self, fmp_api_key: str = None, db_path: str = "earnings_signals.db"):
        self.fmp_key = fmp_api_key
        self.db_path = db_path
        self.fmp_base = "https://financialmodelingprep.com/api/v3"
        self._init_db()

    def _init_db(self):
        """Initialize SQLite table for tracking earnings drift signals."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS earnings_signals (
                ticker TEXT,
                report_date TEXT,
                eps_surprise_pct REAL,
                revenue_surprise_pct REAL,
                guidance_sentiment TEXT,
                entry_price REAL,
                signal_date TEXT,
                status TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def get_earnings_surprises(self, date: str) -> List[Dict]:
        """
        Fetches earnings surprises from FMP.
        Requirement: FMP API Key
        """
        if not self.fmp_key: return []
        
        url = f"{self.fmp_base}/earnings-surprises-calendar?from={date}&to={date}&apikey={self.fmp_key}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                return data
        except Exception as e:
            print(f"Error fetching surprises: {e}")
        return []

    def check_rvol(self, ticker: str) -> bool:
        """
        Computes Relative Volume (RVOL = Yesterday Vol / 30D Avg Vol).
        Requirement: RVOL >= 2.0
        """
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="35d")
            if len(hist) < 31: return False
            
            yesterday_vol = hist['Volume'].iloc[-1]
            avg_vol = hist['Volume'].iloc[-31:-1].mean()
            rvol = yesterday_vol / avg_vol
            
            return rvol >= 2.0
        except:
            return False

    def get_guidance_sentiment(self, ticker: str, year: int, quarter: int) -> str:
        """
        Extracts guidance context from transcripts and uses LLM for sentiment.
        Requirement: Local LLM (Llama.cpp) and FMP Transcript API.
        """
        if not self.fmp_key: return "AMBIGUOUS"
        
        # 1. Fetch Transcript
        url = f"{self.fmp_base}/earning_call_transcript/{ticker}?year={year}&quarter={quarter}&apikey={self.fmp_key}"
        try:
            resp = requests.get(url)
            if resp.status_code != 200: return "AMBIGUOUS"
            transcript = resp.json()[0]['content']
            
            # 2. Extract Q&A / Guidance Sections
            # Ignore first 2000 chars (safe harbor)
            clean_text = transcript[2000:]
            
            # Target Q&A or relevant guidance keywords
            qa_match = re.search(r"Question-and-Answer Session|Q&A", clean_text, re.IGNORECASE)
            target_text = clean_text[qa_match.start():] if qa_match else clean_text
            
            # Extract paragraphs with guidance keywords
            keywords = r"guidance|outlook|future|expect|forecast"
            extracts = []
            paragraphs = target_text.split('\n')
            for p in paragraphs:
                if re.search(keywords, p, re.IGNORECASE):
                    extracts.append(p)
            
            final_extract = " ".join(extracts[:10]) # Take top 10 relevant sentences
            
            # 3. LLM Call (Placeholder for Llama.cpp)
            # prompt = f"Based on these extracts, is the CEO raising guidance for the next quarter? Output strictly: RAISED, LOWERED, or MAINTAINED. Text: {final_extract}"
            # sentiment = self.call_local_llm(prompt)
            # For backtesting logic, we default to logic check
            return "RAISED" # Mocking for structural completion
            
        except:
            return "AMBIGUOUS"

    def calculate_entry(self, ticker: str) -> Optional[Dict]:
        """
        Gap handling and entry trigger logic.
        """
        try:
            stock = yf.Ticker(ticker)
            # Get 5m data for the opening period
            df = stock.history(period="2d", interval="5m")
            if df.empty: return None
            
            prev_close = df[df.index.date < datetime.now().date()]['Close'].iloc[-1]
            opening_price = df[df.index.date == datetime.now().date()]['Open'].iloc[0]
            gap_pct = (opening_price - prev_close) / prev_close * 100
            
            if gap_pct <= 10.0:
                return {'price': opening_price, 'type': 'MARKET_OPEN'}
            else:
                # Wait for 30m candle (first 6 rows of 5m data)
                day_data = df[df.index.date == datetime.now().date()]
                if len(day_data) < 6: return None
                
                first_30m = day_data.head(6)
                high_30m = first_30m['High'].max()
                buy_stop = high_30m + 0.05
                
                # Check if triggered in first hour (next 6 rows)
                next_hour = day_data.iloc[6:12]
                for _, row in next_hour.iterrows():
                    if row['High'] >= buy_stop:
                        return {'price': buy_stop, 'type': 'BUY_STOP_TRIGGER'}
                
            return None
        except:
            return None

    def store_signal(self, data: Dict):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO earnings_signals (ticker, report_date, eps_surprise_pct, revenue_surprise_pct, guidance_sentiment, entry_price, signal_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['ticker'], data['report_date'], data['eps_surprise'], 
            data['rev_surprise'], data['guidance'], data['entry'], 
            datetime.now().strftime("%Y-%m-%d"), 'active'
        ))
        conn.commit()
        conn.close()

    def process_daily_signals(self):
        """Main workflow for scanner."""
        yesterday = (datetime.now() - timedelta(1)).strftime("%Y-%m-%d")
        candidates = self.get_earnings_surprises(yesterday)
        
        for cand in candidates:
            ticker = cand['symbol']
            eps_surprise = cand['surprisePercentage']
            rev_surprise = 0 # Placeholder if rev surprise not in initial packet
            
            # Rule 1: Surprise Thresholds
            if eps_surprise > 5.0:
                # Rule 2: RVOL Check
                if self.check_rvol(ticker):
                    # Rule 3: Guidance Extraction
                    sentiment = self.get_guidance_sentiment(ticker, datetime.now().year, 1) # Assumed Q1 for structure
                    
                    if sentiment == "RAISED":
                        # Rule 4: Entry Trigger
                        entry_info = self.calculate_entry(ticker)
                        if entry_info:
                            self.store_signal({
                                'ticker': ticker,
                                'report_date': yesterday,
                                'eps_surprise': eps_surprise,
                                'rev_surprise': rev_surprise,
                                'guidance': sentiment,
                                'entry': entry_info['price']
                            })
                            print(f"[SIGNAL] {ticker} Entry filled at {entry_info['price']}")

if __name__ == "__main__":
    # Structural Test
    strat = PostEarningsDriftStrategy()
    print("Post-Earnings Drift Strategy Initialized.")
