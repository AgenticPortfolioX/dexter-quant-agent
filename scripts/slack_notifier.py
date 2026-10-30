import os
import requests
import logging
from dotenv import load_dotenv

# Load env from Dexter root
DEXTER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(DEXTER_ROOT, ".env"))

logger = logging.getLogger(__name__)

def send_dexter_slack_alert(message, channel=None, is_error=False):
    """
    Retired Slack Notifier -> Cutover to Buzz Platform.
    Routes trade/market analysis to Buzz #Quantative-Analyst channel
    (UUID: 3038f9b6-a8b8-4208-9b8b-5a48fc0ffa01) and routes all errors,
    bridge disconnects/reconnects, and system triage alerts to #Triage
    (UUID: 2d6095df-ae60-40fd-ac04-28bc150b9508).
    """
    try:
        from scripts.buzz_notifier import (
            send_buzz_message,
            QUANTATIVE_ANALYST_CHANNEL,
            TRIAGE_CHANNEL,
            is_triage_message
        )
        effective_error = bool(is_error or is_triage_message(message))
        target_channel = channel or (TRIAGE_CHANNEL if effective_error else QUANTATIVE_ANALYST_CHANNEL)
        res = send_buzz_message(message, channel=target_channel, is_error=effective_error)
        return bool(res.get("accepted", False))
    except Exception as e:
        logger.error(f"Buzz dispatch error in legacy notifier: {e}")
        return False

if __name__ == "__main__":
    import sys
    test_msg = "Dexter Notifier: Test Connection Successful."
    if len(sys.argv) > 1:
        test_msg = " ".join(sys.argv[1:])
    
    if send_dexter_slack_alert(test_msg, is_error=True):
        print("Alert sent successfully!")
    else:
        print("Failed to send alert. Check .env configuration.")
