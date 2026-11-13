"""
Opencode Unlimited - Doctor for Windows
Comprehensive diagnostics and health check.
"""

import sys
import os
import time
from pathlib import Path

# Add current dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    find_warp_cli,
    find_opencode_cli,
    get_warp_status,
    get_warp_mode,
    get_current_ipv6,
    normalize_prefix_64,
    is_warp_ipv6,
    get_opencode_log_path,
    load_state,
    DEFAULT_PROXY_PORT,
)
from lane_proxy import is_proxy_running

# ANSI color codes for Windows console
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def ok(msg: str):
    print(f"  {GREEN}[OK]{RESET} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}[!]{RESET} {msg}")


def bad(msg: str):
    print(f"  {RED}[FAIL]{RESET} {msg}")


def is_process_running(script_name: str) -> bool:
    try:
        import subprocess
        cmd = f'Get-CimInstance Win32_Process | Where-Object {{ $_.Name -like "python*" -and $_.CommandLine -like "*{script_name}*" }} | Select-Object -ExpandProperty ProcessId'
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=5)
        pids = [p.strip() for p in res.stdout.strip().splitlines() if p.strip()]
        # Filter out self
        my_pid = str(os.getpid())
        return any(p != my_pid for p in pids)
    except Exception:
        return False


def run_doctor():
    # Enable VT100 on Windows terminal
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    print("\n  =========================================")
    print("  Opencode Unlimited - Doctor (Windows)")
    print("  =========================================\n")

    # 1. WARP CLI
    warp_bin = find_warp_cli()
    if warp_bin:
        ok(f"Cloudflare WARP CLI found: {warp_bin}")
    else:
        bad("warp-cli.exe NOT found. Please install Cloudflare WARP.")

    # 2. WARP connection
    if warp_bin:
        st = get_warp_status()
        w_mode, w_port = get_warp_mode()
        if st["connected"]:
            if w_mode == "proxy" and w_port:
                ok(f"WARP tunnel: Connected (Isolated WarpProxy on 127.0.0.1:{w_port} - OpenCode only)")
            else:
                ok("WARP tunnel: Connected (System-wide mode)")
        else:
            bad(f"WARP tunnel: NOT connected ({st['raw'] or 'offline'})")
            print("       Run: warp-cli connect")

    # 3. Egress IPv6 check
    curr_v6 = get_current_ipv6(timeout=5.0)
    if curr_v6:
        prefix = normalize_prefix_64(curr_v6)
        if is_warp_ipv6(curr_v6):
            ok(f"Egress IPv6 is Cloudflare WARP: {curr_v6} (Subnet: {prefix}::/64)")
        else:
            bad(f"Egress IPv6 is NOT WARP! Potential ISP leak: {curr_v6}")
    else:
        warn("No external IPv6 detected. Tunnel may be connecting or inactive.")

    # 4. Smart Lane Proxy
    if is_proxy_running(DEFAULT_PROXY_PORT):
        ok(f"Smart Lane proxy active on 127.0.0.1:{DEFAULT_PROXY_PORT}")
    else:
        warn(f"Smart Lane proxy is idle (it auto-starts when you run 'opencode')")

    # 5. OpenCode CLI
    oc_bin = find_opencode_cli()
    if oc_bin:
        ok(f"OpenCode executable found: {oc_bin}")
    else:
        warn("OpenCode executable not found. Make sure OpenCode is installed.")

    # 6. OpenCode Log
    log_file = get_opencode_log_path()
    if log_file.is_file():
        ok(f"OpenCode log file: {log_file}")
        try:
            with open(log_file, "rb") as f:
                f.seek(max(0, log_file.stat().st_size - 10000))
                tail = f.read()
                if (
                    b"QuotaExceeded" in tail
                    or b"Free usage limit reached" in tail
                    or b"you've used today's free messages" in tail.lower()
                ):
                    warn("Recent log contains QuotaExceeded - rotation recommended if active")
                else:
                    ok("Recent log status: healthy (no active quota wall)")
        except Exception:
            pass
    else:
        warn(f"OpenCode log file not found at {log_file} (will be created when OpenCode runs)")

    # 7. Background Guard
    guard_running = is_process_running("zen_guard.py")
    if guard_running:
        ok("zen-guard watcher: Running in background")
    else:
        warn("zen-guard watcher: Not currently running (run install.ps1 to register background service)")

    # 8. Guard State
    state = load_state()
    hops = state.get("hops", 0)
    b_count = len([x for x in state.get("blacklist", []) if x])
    print(f"\n    Identity stats: {hops} rotations performed | {b_count} blacklisted /64 subnets")

    # 9. Credit file
    credit = Path.home() / ".opencode" / "AGENTS.md"
    if credit.is_file() and "ElectronCursed" in credit.read_text(encoding="utf-8", errors="ignore"):
        ok("Credit configuration (~/.opencode/AGENTS.md): Active")
    else:
        warn("Credit configuration (~/.opencode/AGENTS.md): Missing (auto-generated on launch)")

    print("\n  =========================================")
    print("  Status check complete.")
    print("  To trigger a manual identity rotation, run: opencode-hop")
    print("  =========================================\n")


if __name__ == "__main__":
    run_doctor()
