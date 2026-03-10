
import sys
import os
import unittest
import pandas as pd
import numpy as np

# Add risk manager path
sys.path.append(os.path.join(os.getcwd(), 'rsi_hybrid_reversion'))
from risk_manager import RiskManager

class TestRiskManagerStress(unittest.TestCase):
    def setUp(self):
        # Mock config
        self.config_path = 'rsi_hybrid_reversion/config.yaml'
        self.rm = RiskManager(self.config_path)
        self.initial_equity = 10000
    
    def test_crash_scenario(self):
        """
        Simulate a 20% flash crash in 1 candle.
        Verify SL exits.
        """
        print("\n--- Test: Flash Crash ---")
        entry_price = 100.0
        atr = 1.0 # 1% volatility
        
        # 1. Open Position
        size = self.rm.calculate_position_size('BTC/USDT', entry_price, atr, self.initial_equity)
        levels = self.rm.calculate_trade_levels('BTC/USDT', entry_price, 'buy', atr)
        sl = levels['sl']
        
        print(f"Entry: {entry_price}, Size: {size}, SL: {sl}")
        
        # 2. Crash Candle (Open 100, Low 80, Close 85)
        crash_price = 80.0
        
        # Check if SL Hit
        self.assertTrue(crash_price <= sl, "Stop Loss should be breached")
        
        # Calculate Loss
        # Slippage simulation? 
        # In a real crash, we might fill at 80 (worst case) or somewhere in between.
        # Ensure we don't lose more than expected *too* much (slippage aside).
        
        max_loss = (entry_price - sl) * size
        actual_loss = (entry_price - crash_price) * size
        
        print(f"Max Risk: {max_loss:.2f}, Actual Loss (Slippage): {actual_loss:.2f}")
        # This is just a simulation to see the numbers.
        
    def test_high_volatility_sizing(self):
        """
        Verify position size reduces as ATR increases.
        """
        print("\n--- Test: High Volatility Sizing ---")
        price = 100.0
        
        atr_low = 1.0 # 1%
        atr_high = 5.0 # 5%
        
        size_low = self.rm.calculate_position_size('BTC/USDT', price, atr_low, self.initial_equity)
        size_high = self.rm.calculate_position_size('BTC/USDT', price, atr_high, self.initial_equity)
        
        print(f"Size (ATR 1%): {size_low}")
        print(f"Size (ATR 5%): {size_high}")
        
        self.assertTrue(size_high < size_low, "Size should decrease as Volatility increases")
        self.assertTrue(size_high > 0, "Size should be positive")
        
    def test_trailing_stop_logic(self):
        """
        Verify trailing stop moves up as price increases.
        """
        print("\n--- Test: Trailing Stop ---")
        entry = 100.0
        atr = 1.0
        side = 'buy'
        initial_sl = 98.0
        
        # Price moves to 103 (3R)
        # Trailing activation is usually 2R
        current_price = 103.0
        
        new_sl = self.rm.check_trailing_stop(current_price, entry, side, atr, initial_sl)
        
        print(f"Price: {current_price}, Initial SL: {initial_sl}, New SL: {new_sl}")
        
        self.assertTrue(new_sl > initial_sl, "Trailing Stop should have moved up")

if __name__ == '__main__':
    unittest.main()
