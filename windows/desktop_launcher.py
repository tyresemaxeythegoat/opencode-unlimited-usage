"""
Opencode Unlimited - Desktop Launcher for Windows
Launches the OpenCode Desktop Electron application with Smart Lane IPv6 edge routing
and device identity isolation.
"""

import sys
import os
import socket
import subprocess
import time
from pathlib import Path

# Add current dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    DEFAULT_PROXY_PORT,
    find_warp_cli,
    ensure_credit_file,
)
from zen_lane import prepare_environment
from lane_proxy import is_proxy_running


def find_opencode_desktop() -> str | None:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "Programs", "ai.opencode.desktop", "OpenCode.exe"),
        os.path.join(local_app_data, "Programs", "OpenCode", "OpenCode.exe"),
        r"C:\Program Files\OpenCode\OpenCode.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def is_guard_running() -> bool:
    try:
        cmd = 'Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*zen_guard.py*" } | Select-Object -ExpandProperty ProcessId'
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=5)
        pids = [p.strip() for p in res.stdout.strip().splitlines() if p.strip()]
        return len(pids) > 0
    except Exception:
        return False


def ensure_guard_active():
    if is_guard_running():
        return

    python_exe = sys.executable
    pythonw_candidate = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    launcher = pythonw_candidate if os.path.isfile(pythonw_candidate) else python_exe

    guard_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zen_guard.py")
    flags = 0
    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    subprocess.Popen([launcher, guard_script], creationflags=flags, close_fds=True)


def ensure_proxy_active(preferred_port: int = DEFAULT_PROXY_PORT) -> int:
    if is_proxy_running(preferred_port):
        return preferred_port

    python_exe = sys.executable
    pythonw_candidate = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    launcher = pythonw_candidate if os.path.isfile(pythonw_candidate) else python_exe
    proxy_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lane_proxy.py")

    flags = 0
    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [launcher, proxy_script, "--port", str(preferred_port)],
        creationflags=flags,
        close_fds=True,
    )

    for _ in range(20):
        if is_proxy_running(preferred_port):
            return preferred_port
        time.sleep(0.1)
    return 0


def main():
    # 1. Enforce credit file
    ensure_credit_file()

    # 2. Find OpenCode.exe
    desktop_exe = find_opencode_desktop()
    if not desktop_exe:
        sys.stderr.write("Error: OpenCode desktop application (OpenCode.exe) was not found.\n")
        sys.stderr.write("Checked: %LOCALAPPDATA%\\Programs\\ai.opencode.desktop\\OpenCode.exe\n")
        sys.exit(1)

    # 3. Ensure background guard and persistent Smart Lane proxy are running
    ensure_guard_active()
    port = ensure_proxy_active(DEFAULT_PROXY_PORT)

    # 4. Prepare isolated environment (includes NO_PROXY for 127.0.0.1/localhost/hostname)
    env = prepare_environment(port)

    # 5. Build command line with Chromium proxy flag + explicit loopback bypass
    # Note: do NOT pass '<-loopback>' in Chromium --proxy-bypass-list (it disables loopback bypass!)
    hostname = socket.gethostname()
    cmd = [desktop_exe]
    if port > 0:
        cmd.append(f"--proxy-server=http://127.0.0.1:{port}")
        cmd.append(f"--proxy-bypass-list=127.0.0.1;localhost;[::1];<local>;{hostname}")
    cmd.extend(sys.argv[1:])

    # 6. Launch OpenCode Desktop detached
    flags = 0
    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        cmd,
        env=env,
        creationflags=flags,
        close_fds=True,
    )

    print(f"OpenCode Desktop launched with Smart Lane (PID: {proc.pid})")


if __name__ == "__main__":
    main()
