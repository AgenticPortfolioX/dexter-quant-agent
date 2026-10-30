
# --- Leveraged Bitcoin ETF Execution Protocol ---
# All Bitcoin strategies exclusively trade BITU (2x Long) and SBIT (2x Short).
# Direct trading of IBIT or BTC is strictly prohibited.
LONG_ETF = "BITU"
SHORT_ETF = "SBIT"

def resolve_etf_target(direction: str) -> dict:
    """
    Maps trading signals to 2x leveraged Bitcoin ETFs.
    LONG -> Buy BITU
    SHORT -> Buy SBIT
    """
    d = direction.upper()
    if d in ["BUY", "LONG", "BULLISH"]:
        return {
            "symbol": LONG_ETF,
            "action": "BUY",
            "side": "LONG",
            "leverage": "2x Long",
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.04
        }
    elif d in ["SELL", "SHORT", "BEARISH"]:
        return {
            "symbol": SHORT_ETF,
            "action": "BUY",
            "side": "SHORT",
            "leverage": "2x Inverse Short",
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.04
        }
    return None
