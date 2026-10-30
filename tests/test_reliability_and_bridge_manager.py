import os
import sys
import time
import json
from unittest.mock import patch, MagicMock

# Set stdout/stderr encoding
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

project_root = r"C:\Users\jmgra\antigravityagents\dexter-quant-agent"
if project_root not in sys.path:
    sys.path.append(project_root)

from live_monitor import (
    BrokerBridgeManager,
    write_heartbeat_status,
    HEARTBEAT_STATUS_FILE
)
from strategies.validation.alpha_autotrader import (
    record_etf_entry,
    load_etf_positions,
    save_etf_positions,
    ETF_POSITIONS_FILE
)

def run_tests():
    print("=== RUNNING DESKTOP RELIABILITY & BRIDGE MANAGER TESTS ===")
    
    # Backup ETF positions file
    etf_backup = None
    if os.path.exists(ETF_POSITIONS_FILE):
        with open(ETF_POSITIONS_FILE, "r") as f: etf_backup = f.read()

    try:
        # TEST 1: Heartbeat Status File with Open ETF Positions & Broker Response (Task 1)
        print("\n--- TEST 1: Heartbeat Status File Verification ---")
        record_etf_entry("BITU", 35.00, "LONG", 5.0, "BigD (PO3/AMD)")
        record_etf_entry("SBIT", 25.00, "SHORT", 10.0, "LittleD (SFP)")

        mgr = BrokerBridgeManager(port=5005)
        mgr.is_connected = True
        mgr.last_response = {
            "timestamp": "2026-10-25 09:30:15 EST",
            "status": "ONLINE",
            "http_code": 200,
            "latency_ms": 28.4,
            "logged_in": True,
            "error": None
        }

        with patch("live_monitor.get_etf_realtime_price", side_effect=lambda s: 36.50 if s == "BITU" else 24.20):
            write_heartbeat_status(
                state="LIVE_MARKET",
                status_msg="TRADING (Full Alpha Mode)",
                cycle_count=42,
                start_time=time.time() - 630,
                bridge_mgr=mgr,
                last_error=None,
                cycle_duration=0.25
            )

        assert os.path.exists(HEARTBEAT_STATUS_FILE), "Heartbeat file must exist"
        with open(HEARTBEAT_STATUS_FILE, "r", encoding="utf-8") as f:
            hb = json.load(f)

        assert hb["pid"] == os.getpid()
        assert hb["cycle_count"] == 42
        assert hb["status"] == "NOMINAL"
        assert "BITU" in hb["open_etf_positions"]
        assert "SBIT" in hb["open_etf_positions"]
        assert hb["open_etf_positions"]["BITU"]["current_price"] == 36.50
        assert hb["open_etf_positions"]["BITU"]["unrealized_pnl_pct"] == 4.29 # ((36.5-35)/35)*100
        assert hb["last_broker_response"]["latency_ms"] == 28.4
        print(f"PASSED: Heartbeat status file generated with open ETF positions and broker response:")
        print(f"  BITU PnL: {hb['open_etf_positions']['BITU']['unrealized_pnl_pct']}%")
        print(f"  Broker Latency: {hb['last_broker_response']['latency_ms']}ms | Status: {hb['last_broker_response']['status']}")

        # TEST 2: Reconnection Logic & Exponential Backoff (Task 2)
        print("\n--- TEST 2: Broker Bridge Reconnection & Exponential Backoff ---")
        mgr2 = BrokerBridgeManager(port=5005)
        # Mock requests failure
        with patch("requests.get", side_effect=Exception("Connection refused (Port 5005 offline)")):
            with patch.object(mgr2, "_restart_bridge") as mock_restart:
                # 1st failure: backoff is 5s
                ok, status = mgr2.check_health()
                assert not ok
                assert mgr2.consecutive_failures == 1
                assert mock_restart.call_count == 1
                first_restart_ts = mgr2.next_restart_ts

                # Immediate call before backoff expires: should NOT restart again
                mgr2.check_health()
                assert mgr2.consecutive_failures == 2
                assert mock_restart.call_count == 1, "Must respect backoff interval and not restart repeatedly"
                print("PASSED: Backoff throttles rapid restart attempts correctly.")

        # TEST 3: Broker Disconnect Alert (>60s) and Reconnected Alert (Task 3)
        print("\n--- TEST 3: Alerts for Disconnect >60s and Reconnection ---")
        mgr3 = BrokerBridgeManager(port=5005)
        alerts_sent = []
        def mock_slack(msg):
            alerts_sent.append(msg)
            return True

        with patch("live_monitor.send_dexter_slack_alert", side_effect=mock_slack):
            # Simulate failure after 65 seconds of disconnect
            mgr3.last_contact_ts = time.time() - 65
            with patch("requests.get", side_effect=Exception("Connection timeout")):
                with patch.object(mgr3, "_restart_bridge"):
                    mgr3.check_health()
            
            assert any("BROKER BRIDGE DISCONNECTED (>60s)" in a for a in alerts_sent), "Expected disconnect alert"
            print("PASSED: Sent disconnect alert for >60s downtime.")

            # Now simulate recovery
            alerts_sent.clear()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"logged_in": True}
            with patch("requests.get", return_value=mock_resp):
                mgr3.check_health()

            assert any("BROKER BRIDGE RECONNECTED" in a for a in alerts_sent), "Expected reconnected alert"
            print("PASSED: Sent reconnection alert on bridge recovery.")

        print("\n✅ ALL RELIABILITY & BRIDGE TESTS PASSED PERFECTLY!")

    finally:
        if etf_backup:
            with open(ETF_POSITIONS_FILE, "w") as f: f.write(etf_backup)
        elif os.path.exists(ETF_POSITIONS_FILE):
            os.remove(ETF_POSITIONS_FILE)

if __name__ == "__main__":
    run_tests()
