import requests
import json
import os

ENDPOINT = "http://localhost:3001/v1/chat/completions"

PROMPT = """
You are the DeepSeek R1 Reasoning Engine. 
Task: Implement Proposal 11: Kelly Criterion Dynamic Position Sizing for the Dexter Quant Agent.

Architecture Context:
- Main Engine: alpha_autotrader.py
- Registry: strategy_registry.json
- Stats: signal_quality.json (schema: {"strategies": {"Name": {"win_rate": 60, "avg_win": 1.2, "avg_loss": 0.5, "total_trades": 10}}})
- Global Config: POSITION_SIZE_USD = 25.0, MAX_CONCURRENT_TRADES = 4.

Logic Requirements:
1. Kelly Criterion Formula: f* = (bp - q) / b
   - p = win_rate / 100
   - b = avg_win / avg_loss (net odds)
   - q = 1 - p
2. Multiplier: Use half-Kelly (f_star / 2) for safety.
3. Scaling: Map the Kelly fraction (e.g., 0.10 allocation) to the base size ($25). If kelly_fraction = 0.20, size = $50.
4. Bounds: Minimum $5.00, Maximum $50.00.
5. Cold Start: If strategy has < 3 total trades, use the base $25.00 size.
6. Caution Mode: If CAUTION_MODE is True (Proposal 7), multiply the final calculated size by 0.5.
7. Integration: Provide a 'calculate_kelly_size(strategy_name, price)' function and the updated 'execute_trade' function.

Please reason through the implementation and provide the clean Python code for the integration.
"""

def delegate_to_r1():
    print("🧠 Delegating to DeepSeek R1 Reasoning Engine...")
    payload = {
        "messages": [
            {"role": "user", "content": PROMPT}
        ],
        "temperature": 0.6
    }
    
    try:
        response = requests.post(ENDPOINT, json=payload, timeout=120)
        if response.status_code == 200:
            result = response.json()
            reasoning_and_code = result['choices'][0]['message']['content']
            print("\n--- R1 REASONING AND CODE ---\n")
            print(reasoning_and_code)
            
            # Save to a temporary file for the Orchestrator to read
            with open("r1_proposal_11.txt", "w", encoding="utf-8") as f:
                f.write(reasoning_and_code)
            print("\n✅ R1 output saved to r1_proposal_11.txt")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    delegate_to_r1()
