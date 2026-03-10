import os
import sys
import json
from datetime import datetime

# Add momentum path for cross-imports
momentum_root = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent\strategies\momentum"
if momentum_root not in sys.path:
    sys.path.append(momentum_root)

# Import the Scouts and the Gatekeeper
try:
    from post_earnings_drift.strategy import PostEarningsDriftStrategy
    from sector_rotation.strategy import SectorRotationStrategy
    from value_trap_filter.strategy import ValueTrapFilter
    from follow_the_leader.strategy import FollowTheLeaderStrategy
    from supply_chain_ripple.strategy import SupplyChainRippleStrategy
    from analyst_consensus_shift.strategy import AnalystConsensusStrategy
except ImportError as e:
    print(f"[IMPORT ERROR] Ensure all strategy folders contain strategy.py and __init__.py: {e}")

class MomentumEnsembleOrchestrator:
    """
    The "Master Brain" for Dexter's Momentum Suite.
    Coordinates S1 through S6 while enforcing the S3 (Value Trap) mandate.
    """
    def __init__(self):
        self.s1 = PostEarningsDriftStrategy()
        self.s2 = SectorRotationStrategy()
        self.s3 = ValueTrapFilter()
        self.s4 = FollowTheLeaderStrategy()
        self.s5 = SupplyChainRippleStrategy()
        self.s6 = AnalystConsensusStrategy()
        
        # Position Sizing Map
        self.size_map = {
            'S1': 0.03,
            'S2': 0.025,
            'S4': 0.02,
            'S5': 0.02,
            'S6': 0.03,
            'STACKED_2': 0.06,
            'STACKED_3': 0.08,
            'STACKED_MAX': 0.10
        }

    def run_daily_sync(self):
        print(f"--- DEXTER MOMENTUM ENSEMBLE SYNC: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        # 1. Fetch Narrative Signals (The Scouts)
        # Note: In production, these methods would return lists of tickers identified by the daily scan.
        s1_signals = [] # Earnings Drift Candidates
        s2_signals = [] # Sector Rotation Candidates (Monthly check)
        s4_signals = [] # Insider Buy Candidates
        s5_signals = [] # Supply Chain Ripple Candidates
        s6_signals = [] # Analyst Consensus Shift Candidates
        
        # 2. Combine and Detect Overlap
        all_candidates = set(s1_signals + s2_signals + s4_signals + s5_signals + s6_signals)
        final_portfolio_queue = []

        for ticker in all_candidates:
            # 3. Layer 2: The Quality Gatekeeper (S3)
            # MANDATORY: Every momentum signal must pass the fundamental structural check.
            if not self.s3.validate_quality(ticker):
                print(f"[REJECTED] {ticker} failed S3 Quality Gatekeeper (Solvency/FCF/Safe). Disqualifying signal.")
                continue
            
            # 4. Scoring & Sizing
            # We look for signal overlap to build 'Ultimate Conviction' trades.
            active_signals = []
            if ticker in s1_signals: active_signals.append('S1')
            if ticker in s2_signals: active_signals.append('S2')
            if ticker in s4_signals: active_signals.append('S4')
            if ticker in s5_signals: active_signals.append('S5')
            if ticker in s6_signals: active_signals.append('S6')
            
            narrative_count = len(active_signals)
            
            final_size = 0
            if narrative_count == 1:
                sig_type = active_signals[0]
                final_size = self.size_map.get(sig_type, 0.02)
            elif narrative_count == 2:
                final_size = self.size_map['STACKED_2']
            elif narrative_count == 3:
                final_size = self.size_map['STACKED_3']
            elif narrative_count > 3:
                final_size = self.size_map['STACKED_MAX']
                
            final_portfolio_queue.append({
                'ticker': ticker,
                'weight': final_size,
                'signals': narrative_count
            })

        # 5. Output Execution List
        self._output_execution_plan(final_portfolio_queue)

    def _output_execution_plan(self, items):
        if not items:
            print("[INFO] No signals today passed the Quality Gatekeeper.")
            return

        print("\n🎯 ENSEMBLE EXECUTION PLAN:")
        for item in items:
            conviction = "HIGH" if item['signals'] > 1 else "STANDARD"
            print(f"• BUY {item['ticker']} | Weight: {item['weight']*100}% | Conviction: {conviction}")

if __name__ == "__main__":
    orchestrator = MomentumEnsembleOrchestrator()
    orchestrator.run_daily_sync()
