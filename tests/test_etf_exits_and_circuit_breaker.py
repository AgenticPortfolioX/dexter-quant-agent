import os
import sys
import json
import time
from unittest.mock import patch, MagicMock

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add Project Root to Path
project_root = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
if project_root not in sys.path:
    sys.path.append(project_root)

from strategies.validation.alpha_autotrader import (
    load_etf_positions,
    save_etf_positions,
    record_etf_entry,
    remove_etf_position,
    load_circuit_breaker_state,
    save_circuit_breaker_state,
    is_circuit_breaker_active,
    evaluate_etf_exits_and_circuit_breaker,
    ETF_STOP_LOSS_PCT,
    ETF_TAKE_PROFIT_PCT,
    ETF_MAX_HOLD_MINUTES,
    DAILY_CIRCUIT_BREAKER_PCT,
    ETF_POSITIONS_FILE,
    CIRCUIT_BREAKER_FILE
)

def run_tests():
    print("=== RUNNING LEVERAGED BITCOIN ETF EXIT & CIRCUIT BREAKER TESTS ===")
    
    # Backup original state files if they exist
    pos_backup = None
    cb_backup = None
    if os.path.exists(ETF_POSITIONS_FILE):
        with open(ETF_POSITIONS_FILE, "r") as f: pos_backup = f.read()
    if os.path.exists(CIRCUIT_BREAKER_FILE):
        with open(CIRCUIT_BREAKER_FILE, "r") as f: cb_backup = f.read()
        
    try:
        # TEST 1: Entry Recording (Task 1)
        print("\n--- TEST 1: Entry Recording ---")
        record_etf_entry("BITU", 35.00, "LONG", 2.0, "BigD (PO3/AMD)")
        positions = load_etf_positions()
        assert "BITU" in positions, "BITU should be in tracked ETF positions"
        assert positions["BITU"]["entry_price"] == 35.00, "Entry price must match 35.00"
        assert positions["BITU"]["side"] == "LONG", "Side must be LONG"
        assert positions["BITU"]["quantity"] == 2.0, "Quantity must match 2.0"
        print(f"PASSED: Recorded BITU entry: {positions['BITU']}")

        record_etf_entry("SBIT", 25.00, "SHORT", 3.0, "LittleD (SFP)")
        positions = load_etf_positions()
        assert "SBIT" in positions, "SBIT should be in tracked ETF positions"
        assert positions["SBIT"]["entry_price"] == 25.00, "Entry price must match 25.00"
        assert positions["SBIT"]["side"] == "SHORT", "Side must be SHORT"
        print(f"PASSED: Recorded SBIT entry: {positions['SBIT']}")

        # TEST 2: Stop Loss (-2% on 2x ETF) (Tasks 2, 3, 5)
        print("\n--- TEST 2: Stop Loss Exit ---")
        # Entry 35.00, price drops to 34.20 (-2.28% <= -2.0%)
        executed_trades = []
        def mock_execute(strat_name, ticker, side, price, **kwargs):
            executed_trades.append({"strat": strat_name, "ticker": ticker, "side": side, "price": price})

        with patch("strategies.validation.alpha_autotrader.get_etf_realtime_price", return_value=34.20), \
             patch("strategies.validation.alpha_autotrader.execute_trade", side_effect=mock_execute), \
             patch("strategies.validation.alpha_autotrader.send_quant_alert"):
            
            evaluate_etf_exits_and_circuit_breaker(mode="LIVE_MARKET")
            
            # BITU should have exited on stop loss
            assert any(t["strat"] == "Stop Loss (-2% on 2x ETF)" and t["ticker"] == "BITU" for t in executed_trades), \
                f"Expected Stop Loss (-2% on 2x ETF), got {executed_trades}"
            positions = load_etf_positions()
            assert "BITU" not in positions, "BITU should be removed after exit"
            print(f"PASSED: Stop Loss triggered correctly: {executed_trades[-1]}")

        # TEST 3: Take Profit (+4% on 2x ETF) (Tasks 2, 3, 5)
        print("\n--- TEST 3: Take Profit Exit ---")
        record_etf_entry("BITU", 35.00, "LONG", 2.0, "BigD (PO3/AMD)")
        # Price rises to 36.50 (+4.28% >= +4.0%)
        executed_trades.clear()
        with patch("strategies.validation.alpha_autotrader.get_etf_realtime_price", return_value=36.50), \
             patch("strategies.validation.alpha_autotrader.execute_trade", side_effect=mock_execute), \
             patch("strategies.validation.alpha_autotrader.send_quant_alert"):
            
            evaluate_etf_exits_and_circuit_breaker(mode="LIVE_MARKET")
            
            assert any(t["strat"] == "Take Profit (+4% on 2x ETF)" and t["ticker"] == "BITU" for t in executed_trades), \
                f"Expected Take Profit (+4% on 2x ETF), got {executed_trades}"
            positions = load_etf_positions()
            assert "BITU" not in positions, "BITU should be removed after exit"
            print(f"PASSED: Take Profit triggered correctly: {executed_trades[-1]}")

        # TEST 4: Max Hold Period Force-Exit (Task 4, 5)
        print("\n--- TEST 4: Max Hold Period Force-Exit ---")
        record_etf_entry("BITU", 35.00, "LONG", 2.0, "BigD (PO3/AMD)")
        # Manipulate timestamp to 250 minutes ago (> 240 mins)
        positions = load_etf_positions()
        positions["BITU"]["entry_timestamp"] = time.time() - (250 * 60)
        save_etf_positions(positions)

        executed_trades.clear()
        # Price within SL/TP band (+1.0%)
        with patch("strategies.validation.alpha_autotrader.get_etf_realtime_price", return_value=35.35), \
             patch("strategies.validation.alpha_autotrader.execute_trade", side_effect=mock_execute), \
             patch("strategies.validation.alpha_autotrader.send_quant_alert"):
            
            evaluate_etf_exits_and_circuit_breaker(mode="LIVE_MARKET")
            
            assert any(t["strat"] == "Max Hold Period" and t["ticker"] == "BITU" for t in executed_trades), \
                f"Expected Max Hold Period, got {executed_trades}"
            positions = load_etf_positions()
            assert "BITU" not in positions, "BITU should be removed after max hold exit"
            print(f"PASSED: Max Hold Period triggered correctly: {executed_trades[-1]}")

        # TEST 5: Daily Circuit Breaker (Task 6)
        print("\n--- TEST 5: Daily Circuit Breaker ---")
        record_etf_entry("BITU", 35.00, "LONG", 2.0, "BigD (PO3/AMD)")
        record_etf_entry("SBIT", 25.00, "SHORT", 3.0, "LittleD (SFP)")
        
        # Set starting equity $1000, current equity $950 (drawdown 5.0% >= 4.5%)
        cb_state = load_circuit_breaker_state()
        cb_state["starting_equity"] = 1000.0
        cb_state["peak_equity"] = 1000.0
        cb_state["tripped"] = False
        save_circuit_breaker_state(cb_state)

        executed_trades.clear()
        with patch("strategies.validation.alpha_autotrader.get_current_portfolio_equity", return_value=950.0), \
             patch("strategies.validation.alpha_autotrader.get_etf_realtime_price", return_value=34.50), \
             patch("strategies.validation.alpha_autotrader.execute_trade", side_effect=mock_execute), \
             patch("strategies.validation.alpha_autotrader.send_quant_alert"):
            
            evaluate_etf_exits_and_circuit_breaker(mode="LIVE_MARKET")
            
            assert is_circuit_breaker_active(), "Circuit breaker should be tripped"
            cb_after = load_circuit_breaker_state()
            print(f"Circuit Breaker State: {cb_after}")
            assert cb_after["tripped"] is True, "tripped must be True"
            assert cb_after["drawdown_pct"] >= DAILY_CIRCUIT_BREAKER_PCT, "Drawdown must be >= 4.5%"
            
            # Check both BITU and SBIT were flattened
            assert any(t["ticker"] == "BITU" and "Circuit Breaker" in t["strat"] for t in executed_trades), "BITU must be flattened"
            assert any(t["ticker"] == "SBIT" and "Circuit Breaker" in t["strat"] for t in executed_trades), "SBIT must be flattened"
            
            positions = load_etf_positions()
            assert len(positions) == 0, f"All ETF positions must be flattened, got {positions}"
            print("PASSED: Daily Circuit Breaker tripped, flattened all positions, and locked state.")

        print("\n✅ ALL 5 TEST SUITES PASSED PERFECTLY!")

    finally:
        # Restore or cleanup test state files
        if pos_backup is not None:
            with open(ETF_POSITIONS_FILE, "w") as f: f.write(pos_backup)
        elif os.path.exists(ETF_POSITIONS_FILE):
            os.remove(ETF_POSITIONS_FILE)
            
        if cb_backup is not None:
            with open(CIRCUIT_BREAKER_FILE, "w") as f: f.write(cb_backup)
        elif os.path.exists(CIRCUIT_BREAKER_FILE):
            os.remove(CIRCUIT_BREAKER_FILE)

if __name__ == "__main__":
    run_tests()
