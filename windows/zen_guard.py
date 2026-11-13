"""
Opencode Unlimited - Zen Guard for Windows
Background watcher: monitors opencode.log for quota exhaustion and auto-rotates WARP /64.
"""

import sys
import os
import time
import traceback
from pathlib import Path

# Add current dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    get_opencode_log_path,
    load_state,
    update_state,
    log_guard,
    execute_hop_cycle,
    find_warp_cli,
    is_auto_continue_active,
)

# Handle pythonw.exe where stdout and stderr are None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

def exception_handler(exc_type, exc_value, exc_traceback):
    err = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_guard(f"FATAL EXCEPTION: {err}")

sys.excepthook = exception_handler

COOLDOWN = 60  # seconds between rotations


def run_guard_loop():
    warp_bin = find_warp_cli()
    if not warp_bin:
        sys.stderr.write("zen-guard: warp-cli.exe not found. Exiting.\n")
        sys.exit(1)

    log_path = get_opencode_log_path()
    log_guard(f"zen-guard started (watching: {log_path}, cooldown: {COOLDOWN}s)")

    # Initialize offset if state is fresh
    state = load_state()
    if state.get("offset", 0) == 0 and log_path.is_file():
        try:
            init_size = log_path.stat().st_size
            update_state(lambda s: s.update({"offset": init_size}))
        except Exception:
            pass

    while True:
        try:
            time.sleep(10)

            if not log_path.is_file():
                continue

            try:
                curr_size = log_path.stat().st_size
            except Exception:
                continue

            state = load_state()
            offset = state.get("offset", 0)

            if curr_size < offset:
                # Log was rotated or truncated
                offset = 0

            new_bytes_count = curr_size - offset
            wall_detected = False

            if 0 < new_bytes_count < 50_000_000:
                try:
                    with open(log_path, "rb") as f:
                        f.seek(offset)
                        chunk = f.read(new_bytes_count)
                        if (
                            b"QuotaExceeded" in chunk
                            or b"Free usage limit reached" in chunk
                            or b"AI.Error.QuotaExceeded" in chunk
                            or b"you've used today's free messages" in chunk.lower()
                        ):
                            wall_detected = True
                except Exception as e:
                    log_guard(f"Error reading log: {e}")

            # Update offset atomically without clobbering blacklist/hops
            state = update_state(lambda s: s.update({"offset": curr_size}))

            now = int(time.time())
            last_hop = state.get("last_hop", 0)
            elapsed = now - last_hop

            if wall_detected:
                if is_auto_continue_active():
                    log_guard("Quota wall seen while auto-continue is active - yielding rotation.")
                elif elapsed >= COOLDOWN:
                    log_guard("Quota wall detected! Triggering automatic WARP rotation...")
                    success, old_v6, new_v6 = execute_hop_cycle(max_retries=8)
                    if success:
                        log_guard(f"Auto-rotation complete: {old_v6} -> {new_v6}")
                    else:
                        log_guard("Auto-rotation attempt failed; will retry if error persists.")
                else:
                    log_guard(f"Quota error seen, but within cooldown ({elapsed}s < {COOLDOWN}s) - waiting.")

        except KeyboardInterrupt:
            log_guard("zen-guard stopped by user.")
            break
        except Exception as e:
            log_guard(f"Unexpected error in guard loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_guard_loop()
