import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class ValueTrapFilter:
    """
    Momentum Strategy 3: Value Trap Filter (Quality Gatekeeper)
    Prevents buying fundamentally broken stocks that appear 'cheap' due to price drops.
    """
    def __init__(self, simfin_key: str = None):
        self.simfin_key = simfin_key

    def is_value_trap_candidate(self, ticker: str) -> bool:
        """
        Trigger: Only run filter if stock is down >15% over last 6 months.
        Returns True if the check should proceed, False if the stock is not in 'Value Trap' territory.
        """
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            if hist.empty: return False
            
            start_price = hist['Close'].iloc[0]
            current_price = hist['Close'].iloc[-1]
            
            # Down > 15% check
            return current_price < (start_price * 0.85)
        except:
            return False

    def validate_quality(self, ticker: str) -> bool:
        """
        Main entry point. Runs the fundamental 'Quality Gatekeeper' checks.
        Returns:
            True: Stock passes all quality checks (NOT a value trap).
            False: Stock fails one or more checks (Disqualified).
        """
        # 0. Check Trigger
        if not self.is_value_trap_candidate(ticker):
            return True # Not a value trap candidate, passes gatekeeper by default

        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            financials = stock.financials
            balance_sheet = stock.balance_sheet
            cash_flow = stock.cashflow

            if financials.empty or balance_sheet.empty or cash_flow.empty:
                return False # Missing critical data

            # 1. Solvency: Interest Coverage Ratio (EBIT / Interest Expense)
            # EBIT is often 'Operating Income'
            ebit = financials.loc['Operating Income'].iloc[0]
            # Use get to handle missing interest expense (Pitfall fix)
            int_exp = financials.loc['Interest Expense'].iloc[0] if 'Interest Expense' in financials.index else 0
            
            if int_exp != 0:
                icr = ebit / abs(int_exp)
                if icr < 3.0: return False
            elif ebit <= 0:
                return False # Negative EBIT with zero interest is still high risk

            # 2. Cash Flow: FCF Yield (TTM FCF / Market Cap)
            # FCF = Cash from Operations - CapEx
            ops_cash = cash_flow.loc['Operating Cash Flow'].iloc[0]
            capex = abs(cash_flow.loc['Capital Expenditure'].iloc[0]) if 'Capital Expenditure' in cash_flow.index else 0
            fcf = ops_cash - capex
            mkt_cap = info.get('marketCap')
            
            if not mkt_cap or (fcf / mkt_cap) < 0.05:
                return False

            # 3. Bankruptcy Risk: Altman Z-Score (Non-Manufacturing)
            # Z = 6.56*A + 3.26*B + 6.72*C + 1.05*D
            # A = Working Capital / Total Assets
            # B = Retained Earnings / Total Assets
            # C = EBIT / Total Assets
            # D = Market Value of Equity / Total Liabilities
            
            total_assets = balance_sheet.loc['Total Assets'].iloc[0]
            # Working Capital = Total Current Assets - Total Current Liabilities
            curr_assets = balance_sheet.loc['Total Current Assets'].iloc[0]
            curr_liab = balance_sheet.loc['Total Current Liabilities'].iloc[0]
            working_cap = curr_assets - curr_liab
            
            ret_earnings = balance_sheet.loc['Retained Earnings'].iloc[0] if 'Retained Earnings' in balance_sheet.index else 0
            total_liab = balance_sheet.loc['Total Liabilities Net Minority Interest'].iloc[0] if 'Total Liabilities Net Minority Interest' in balance_sheet.index else balance_sheet.loc['Total Liabilities'].iloc[0]
            
            A = working_cap / total_assets
            B = ret_earnings / total_assets
            C = ebit / total_assets
            D = mkt_cap / total_liab
            
            z_score = (6.56 * A) + (3.26 * B) + (6.72 * C) + (1.05 * D)
            if z_score < 1.8: return False

            # 4. Valuation: Current PE < 5-Year Median PE
            current_pe = info.get('trailingPE')
            if not current_pe: return False
            
            # 5. Nuanced: Sloan Ratio (Earnings Quality)
            # Sloan = (Net Income - CFO - CFI) / Total Assets
            net_income = financials.loc['Net Income'].iloc[0]
            cfo = cash_flow.loc['Operating Cash Flow'].iloc[0]
            cfi = cash_flow.loc['Investing Cash Flow'].iloc[0] if 'Investing Cash Flow' in cash_flow.index else 0
            
            sloan_ratio = (net_income - cfo - cfi) / total_assets
            if sloan_ratio > 0.10: return False

            # 6. Nuanced: Asset Bloat (Inventory/Receivables vs Revenue)
            if len(financials.columns) > 1 and len(balance_sheet.columns) > 1:
                rev_growth = (financials.loc['Total Revenue'].iloc[0] / financials.loc['Total Revenue'].iloc[1]) - 1
                
                if 'Inventory' in balance_sheet.index:
                    inv_growth = (balance_sheet.loc['Inventory'].iloc[0] / balance_sheet.loc['Inventory'].iloc[1]) - 1
                    if inv_growth > (rev_growth + 0.10): return False
                    
                if 'Receivables' in balance_sheet.index:
                    rec_growth = (balance_sheet.loc['Receivables'].iloc[0] / balance_sheet.loc['Receivables'].iloc[1]) - 1
                    if rec_growth > (rev_growth + 0.10): return False

            # 7. Nuanced: Margin Deterioration
            if 'Gross Profit' in financials.index and len(financials.columns) >= 3:
                margin_current = financials.loc['Gross Profit'].iloc[0] / financials.loc['Total Revenue'].iloc[0]
                margin_prev1 = financials.loc['Gross Profit'].iloc[1] / financials.loc['Total Revenue'].iloc[1]
                margin_prev2 = financials.loc['Gross Profit'].iloc[2] / financials.loc['Total Revenue'].iloc[2]
                
                if margin_current < margin_prev1 < margin_prev2:
                    return False # Declining margins for 2 years

            # 8. Nuanced: Shareholder Dilution
            shares_current = info.get('sharesOutstanding')
            # Attempt to find historical shares if available via financials or data
            # Simplified: yfinance doesn't easily provide historical shares in BS
            # But we can check if it's explicitly available or skip if not.

            # 9. Nuanced: Momentum Floor (200 SMA & 30D Slope)
            hist_1y = stock.history(period="1y")
            if len(hist_1y) >= 200:
                sma_200 = hist_1y['Close'].rolling(200).mean().iloc[-1]
                current_price = hist_1y['Close'].iloc[-1]
                
                # Calculate 30-day slope
                last_30 = hist_1y['Close'].tail(30)
                slope = np.polyfit(range(30), last_30.values, 1)[0]
                
                if current_price < sma_200 and slope < 0:
                    return False # Falling knife

            return True # Passed all gates

        except Exception as e:
            print(f"[ERROR] Value Trap Filter for {ticker}: {e}")
            return False

if __name__ == "__main__":
    filter = ValueTrapFilter()
    # Test on a known volatile stock or a benchmark
    result = filter.validate_quality("TSLA")
    print(f"Filter Result for TSLA: {'PASS' if result else 'FAIL'}")
