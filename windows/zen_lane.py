"""
Opencode Unlimited - Zen Lane for Windows
Launches OpenCode with IPv6 pinning, dynamic edge rotation, and machine-id isolation.
"""

import sys
import os
import uuid
import time
import socket
import threading
import subprocess
from pathlib import Path

# Add current dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    DEFAULT_PROXY_PORT,
    get_base_dir,
    find_opencode_cli,
    ensure_credit_file,
)
from lane_proxy import (
    ThreadingHTTPServer,
    SmartLaneProxyHandler,
    is_proxy_running,
)


def start_embedded_proxy(preferred_port: int = DEFAULT_PROXY_PORT) -> tuple[int, ThreadingHTTPServer | None]:
    """
    Ensure a Smart Lane proxy is available. If an external instance is running,
    reuse it. Otherwise, spawn an embedded daemon thread on an available port.
    """
    if is_proxy_running(preferred_port):
        return preferred_port, None

    # Try preferred port, fallback to sequential or dynamic port
    ports_to_try = [preferred_port, preferred_port + 1, preferred_port + 2, 0]
    server = None
    actual_port = 0

    for port in ports_to_try:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), SmartLaneProxyHandler)
            actual_port = server.server_address[1]
            break
        except OSError:
            continue

    if not server:
        # Fallback without proxy
        return 0, None

    # Start proxy in background daemon thread
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Small yield for thread startup
    time.sleep(0.05)
    return actual_port, server


def prepare_environment(port: int) -> dict:
    """Build isolated environment with proxy and randomized device identity"""
    env = os.environ.copy()

    if port > 0:
        proxy_url = f"http://127.0.0.1:{port}"
        env["HTTP_PROXY"] = proxy_url
        env["HTTPS_PROXY"] = proxy_url
        env["ALL_PROXY"] = proxy_url
        env["http_proxy"] = proxy_url
        env["https_proxy"] = proxy_url
        env["all_proxy"] = proxy_url
        hostname = socket.gethostname()
        no_proxy = f"127.0.0.1,localhost,::1,[::1],{hostname}"
        env["NO_PROXY"] = no_proxy
        env["no_proxy"] = no_proxy

    # Random machine GUID per launch
    random_guid = str(uuid.uuid4())
    env["OPENCODE_MACHINE_ID"] = random_guid
    env["MACHINE_ID"] = random_guid
    env["DEVICE_ID"] = random_guid

    # Also persist to shim directory for apps that read machine-guid.txt
    shim_dir = get_base_dir() / "shim"
    shim_dir.mkdir(parents=True, exist_ok=True)
    try:
        (shim_dir / "machine-guid.txt").write_text(random_guid, encoding="utf-8")
    except Exception:
        pass

    return env


def main():
    # 1. Ensure credit sign-off file is intact
    ensure_credit_file()

    # 2. Find OpenCode binary
    real_bin = find_opencode_cli()
    if not real_bin:
        sys.stderr.write("Error: OpenCode binary not found.\n")
        sys.stderr.write("Please install OpenCode or set OUC_REAL_BIN to its full path.\n")
        sys.exit(1)

    # 3. Ensure Smart Lane proxy is active
    port, server = start_embedded_proxy(DEFAULT_PROXY_PORT)

    # 4. Prepare execution environment
    env = prepare_environment(port)
    args = sys.argv[1:]

    # Check if this is a non-interactive 'run' invocation
    is_run = len(args) > 0 and args[0] == "run"
    is_piped = not sys.stdout.isatty()

    try:
        if is_run and is_piped:
            # Piped run: append credit line deterministically if needed
            proc = subprocess.Popen(
                [real_bin] + args,
                env=env,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            out, _ = proc.communicate()
            if out:
                sys.stdout.write(out)
                if "Telegram:- @ElectronCursed" not in out:
                    if not out.endswith("\n"):
                        sys.stdout.write("\n")
                    sys.stdout.write("Telegram:- @ElectronCursed\n")
            sys.exit(proc.returncode)

        # Interactive TUI mode - run directly in current console
        res = subprocess.run([real_bin] + args, env=env)
        sys.exit(res.returncode)

    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        if server:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
