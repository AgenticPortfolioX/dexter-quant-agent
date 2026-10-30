
import os
import subprocess
import json
import sys
from pathlib import Path

# Paths
TRADING_AGENTS_ROOT = Path(r"C:\Users\jmgra\antigravityagents\.agent\workflows\TradingAgents")
SERVICE_BRIDGE = TRADING_AGENTS_ROOT / "service_bridge.py"
TA_VENV_PYTHON = TRADING_AGENTS_ROOT / "venv" / "Scripts" / "python.exe"

def validate_signal(ticker, signal_type, timeframe="2-4 week timeframe"):
    """
    Calls the TradingAgents research bridge to validate a quantitative signal.
    Returns: (verdict, confidence, reasoning_summary)
    """
    if not TA_VENV_PYTHON.exists():
        return "ERROR", 0, "TradingAgents VENV not found."
    
    note = f"Dexter Quant Signal: {signal_type} for {timeframe}"
    cmd = [
        str(TA_VENV_PYTHON),
        str(SERVICE_BRIDGE),
        "--ticker", ticker,
        "--note", note
    ]
    
    try:
        # Run with a 10-minute timeout for qualitative synthesis
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, encoding='utf-8')
        
        if result.returncode != 0:
            return "ERROR", 0, f"Bridge failed: {result.stderr}"
            
        # Parse the JSON output from the bridge
        # The bridge prints the JSON result at the end
        output_lines = result.stdout.strip().split('\n')
        json_str = ""
        for line in reversed(output_lines):
            if line.strip().startswith('{') and line.strip().endswith('}'):
                json_str = line.strip()
                break
        
        if not json_str:
            # Try to find JSON block in full output
            import re
            match = re.search(r'\{.*\}', result.stdout, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                return "ERROR", 0, "Could not find JSON verdict in bridge output."

        data = json.loads(json_str)
        verdict = data.get("decision", "HOLD").upper()
        confidence = data.get("confidence", 0)
        reasoning = data.get("reasoning", "No reasoning provided.")
        
        return verdict, confidence, reasoning
        
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 0, "Qualitative research timed out."
    except Exception as e:
        return "ERROR", 0, f"Validator error: {str(e)}"

if __name__ == "__main__":
    # Test call
    if len(sys.argv) > 1:
        t = sys.argv[1]
        s = sys.argv[2] if len(sys.argv) > 2 else "BUY"
        print(f"Validating {s} signal for {t}...")
        v, c, r = validate_signal(t, s)
        print(f"Verdict: {v} ({c*100:.1f}% Confidence)")
        print(f"Reasoning: {r}")
