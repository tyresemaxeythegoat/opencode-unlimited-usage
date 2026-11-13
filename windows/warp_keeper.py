"""
Opencode Unlimited - WARP Keeper for Windows
Watchdog loop: ensures Cloudflare WARP remains connected in 'warp' mode.
"""

import sys
import os
import time

# Handle pythonw.exe where stdout and stderr are None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Add current dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    find_warp_cli,
    run_warp,
    get_warp_status,
    log_guard,
)

TICK = 45  # seconds


def run_keeper_loop():
    warp_bin = find_warp_cli()
    if not warp_bin:
        sys.stderr.write("warp-keeper: warp-cli.exe not found.\n")
        sys.exit(1)

    log_guard("warp-keeper watchdog started.")

    while True:
        try:
            # Enforce warp mode
            run_warp(["mode", "warp"])

            # Check status
            st = get_warp_status()
            if not st["connected"]:
                log_guard("WARP tunnel disconnected - reconnecting...")
                run_warp(["connect"])
                time.sleep(4)
                st = get_warp_status()
                if not st["connected"]:
                    # If still disconnected, refresh registration
                    log_guard("Reconnecting failed, refreshing registration...")
                    run_warp(["disconnect"])
                    run_warp(["registration", "delete"])
                    run_warp(["registration", "new"])
                    run_warp(["mode", "warp"])
                    run_warp(["connect"])

            time.sleep(TICK)

        except KeyboardInterrupt:
            log_guard("warp-keeper stopped by user.")
            break
        except Exception as e:
            log_guard(f"Unexpected error in keeper: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run_keeper_loop()
