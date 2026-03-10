import sys
import json
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy_id", type=str)
    args = parser.parse_args()

    # Mock backtesting logic
    # import qlib
    # ... backtest ...

    result = {
        "status": "success",
        "message": "Backtest completed",
        "strategy_id": args.strategy_id,
        "performance": {
            "sharpe": 1.55,
            "annual_return": 0.22,
            "max_drawdown": -0.09,
            "win_rate": 0.58
        }
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
