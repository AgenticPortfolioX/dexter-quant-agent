"""
Buzz Platform Notifier for Robinhood Trader
-------------------------------------------
Publishes pre-market reports, post-market reports, and quant analysis to Buzz.
Home Channel: #Quantative-Analyst (UUID: 3038f9b6-a8b8-4208-9b8b-5a48fc0ffa01)
Triage Channel: #Triage (UUID: 2d6095df-ae60-40fd-ac04-28bc150b9508)
Relay: wss://gramsagency.communities.buzz.xyz

Posting Rules (Permanent):
- Flat messages, never threads (no --reply-to).
- No hashtags, no emojis, American spelling, normal capitalization, markdown fine.
- Quantitative-Analyst = markets, equities, trade analysis only.
- Data timestamp and source clearly stated.
- Errors and system/bridge triage alerts routed strictly to #Triage.
"""

import os
import sys
import subprocess
import json
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# Constants
EST = pytz.timezone('US/Eastern')
QUANTATIVE_ANALYST_CHANNEL = "3038f9b6-a8b8-4208-9b8b-5a48fc0ffa01"
TRIAGE_CHANNEL = "2d6095df-ae60-40fd-ac04-28bc150b9508"
NOTIFICATIONS_CHANNEL = "48a0070d-3596-4d07-92a6-3a9362393d62"
DELIVERABLES_CHANNEL = "41245ad4-b799-438f-8022-01c787feac8d"

# Any message matching these operational/error/system signatures is automatically routed to #Triage
TRIAGE_SIGNATURES = (
    "BROKER BRIDGE DISCONNECTED",
    "BROKER BRIDGE RECONNECTED",
    "DEXTER MONITOR STARTED",
    "DEXTER MONITOR RESTARTED",
    "MONITOR STARTED / RESTARTED",
    "DAILY CIRCUIT BREAKER TRIPPED",
    "ORDER REJECTED",
    "CRITICAL ERROR",
    "CRITICAL LOOP EXCEPTION",
    "EXECUTION FAILURE",
    "HTTPCONNECTIONPOOL",
    "MAX RETRIES EXCEEDED",
    "CONNECTIONREFUSEDERROR",
    "BRIDGE ON PORT 5005 UNREACHABLE",
    "AUTH_REQUIRED",
    "SESSION EXPIRED",
    "FAILED TO EXECUTE",
    "ZOMBIE",
    "EXCEPTION",
    "TRACEBACK",
)

DEXTER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUZZ_ENV_FILE = os.path.join(DEXTER_ROOT, "config", "buzz.env")
BUZZ_CLI_PATH = r"C:\Users\jmgra\.cargo\bin\buzz.exe"

def load_buzz_env():
    env_vars = os.environ.copy()
    if os.path.exists(BUZZ_ENV_FILE):
        with open(BUZZ_ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

def is_triage_message(text: str) -> bool:
    """Detects whether a message is an error, system alert, or bridge status message that belongs in #Triage."""
    if not text:
        return False
    upper = text.upper()
    return any(sig in upper for sig in TRIAGE_SIGNATURES)

def clean_buzz_message(text: str) -> str:
    """Removes emojis and hashtags per Buzz channel etiquette."""
    import re
    # Remove common emoji unicode ranges
    emoji_pattern = re.compile(
        r'[\U0001F600-\U0001F64F]'  # emoticons
        r'|[\U0001F300-\U0001F5FF]' # symbols & pictographs
        r'|[\U0001F680-\U0001F6FF]' # transport & map symbols
        r'|[\U0001F1E0-\U0001F1FF]' # flags
        r'|[\U00002702-\U000027B0]'
        r'|[\U000024C2-\U0001F251]'
        r'|[\U0001F900-\U0001F9FF]' # supplemental symbols
        r'|[\U0001FA70-\U0001FAFF]'
        r'|[\U00002600-\U000026FF]'
        r'|[🚨⚠️🔥✅🛑📊📈🪙🔋🚀🧪💡🔄🩹🏁]',
        flags=re.UNICODE
    )
    clean = emoji_pattern.sub('', text)
    # Remove hashtags if any
    clean = re.sub(r'#(\w+)', r'\1', clean)
    # Collapse multiple blank lines
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
    return clean

def send_buzz_message(content: str, channel: str = QUANTATIVE_ANALYST_CHANNEL, is_error: bool = False) -> dict:
    """
    Sends a signed Nostr message to a Buzz channel via buzz CLI.
    Uses stdin pipe to prevent escaping and length issues.
    Automatically routes errors and system/bridge triage events to TRIAGE_CHANNEL.
    """
    if is_error or is_triage_message(content):
        channel = TRIAGE_CHANNEL

    clean_content = clean_buzz_message(content)
    if not clean_content:
        return {"accepted": False, "error": "Empty message after cleaning"}

    env_vars = load_buzz_env()
    cli_path = env_vars.get("BUZZ_CLI_PATH", BUZZ_CLI_PATH)

    if not os.path.exists(cli_path):
        err_msg = f"Buzz CLI binary not found at {cli_path}"
        logger.error(err_msg)
        return {"accepted": False, "error": err_msg}

    cmd = [cli_path, "messages", "send", "--channel", channel, "--content", "-"]

    try:
        proc = subprocess.run(
            cmd,
            input=clean_content,
            env=env_vars,
            capture_output=True,
            text=True,
            timeout=20
        )

        if proc.returncode == 0:
            try:
                res = json.loads(proc.stdout)
                return res
            except Exception:
                return {"accepted": True, "output": proc.stdout.strip()}
        else:
            err_json = {}
            try:
                err_json = json.loads(proc.stderr)
            except Exception:
                err_json = {"error": "cli_error", "message": proc.stderr.strip(), "exit_code": proc.returncode}
            
            logger.warning(f"Buzz message send returned exit code {proc.returncode}: {err_json}")
            return {"accepted": False, "error": err_json, "exit_code": proc.returncode}

    except Exception as e:
        logger.error(f"Buzz send failed with exception: {e}")
        return {"accepted": False, "error": str(e)}

def upload_buzz_file(file_path: str) -> dict:
    """Uploads a file to Blossom storage on the Buzz relay."""
    if not os.path.exists(file_path):
        return {"error": "file_not_found"}

    env_vars = load_buzz_env()
    cli_path = env_vars.get("BUZZ_CLI_PATH", BUZZ_CLI_PATH)

    cmd = [cli_path, "upload", "file", "--file", file_path]
    try:
        proc = subprocess.run(cmd, env=env_vars, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        else:
            return {"error": proc.stderr.strip()}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    msg = "Robinhood Trader online test. US equities analysis only."
    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
    res = send_buzz_message(msg)
    print("Buzz Dispatch Result:", res)
