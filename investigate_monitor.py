import live_monitor
import traceback
import sys

try:
    print("--- DEXTER INVESTIGATION START ---")
    live_monitor.main(test_once=True)
    print("--- DEXTER INVESTIGATION END ---")
except Exception as e:
    print("--- DEXTER INVESTIGATION CRASH ---")
    traceback.print_exc()
    sys.exit(1)
