"""
Opencode Unlimited - Auto Continue & Unlimit Loop
Handles:
1. Sending 'continue' to the target OpenCode session
2. Waiting for the response; if a free usage limit error occurs
   ("you've used today's free messages" / FreeUsageLimitError / 429):
   - Undoing (reverting & committing) that failed 'continue' message
   - Rotating Cloudflare WARP to a fresh IPv6 /64 subnet
   - Repeating until the quota message is gone and work resumes
"""

import os
import sys
import time
import json
import glob
import argparse
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import core
import zen_lane
from lane_proxy import is_proxy_running


QUOTA_MARKERS = (
    "free usage limit reached",
    "freeusagelimiterror",
    "provider.free-limit",
    "you've used today's free messages",
    "you have used today's free messages",
)


def find_opencode_cli() -> str:
    """Finds the opencode-cli executable on the system."""
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        roaming_clis = sorted(
            glob.glob(os.path.join(appdata, "ai.opencode.desktop", "cli", "*", "opencode-cli.exe")),
            reverse=True,
        )
        if roaming_clis and os.path.exists(roaming_clis[0]):
            return roaming_clis[0]

    cli_path = core.find_opencode_cli()
    if cli_path:
        return cli_path

    raise FileNotFoundError("Could not find opencode-cli.exe on the system.")


def ensure_lane_proxy_running(port: int = core.DEFAULT_PROXY_PORT) -> bool:
    """Ensure the Smart Lane HTTP/CONNECT proxy is active in the background."""
    if is_proxy_running(port):
        return True

    proxy_script = SCRIPT_DIR / "lane_proxy.py"
    if not proxy_script.is_file():
        return False

    py_dir = Path(sys.executable).parent
    pythonw = py_dir / "pythonw.exe"
    exe = str(pythonw) if pythonw.is_file() else sys.executable

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )

    try:
        subprocess.Popen(
            [exe, str(proxy_script), "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    except Exception as e:
        print(f"  Warning: failed to start Smart Lane proxy: {e}")
        return False

    for _ in range(15):
        if is_proxy_running(port):
            return True
        time.sleep(0.2)
    return is_proxy_running(port)


def _get_proxy_marker_file() -> Path:
    return core.get_state_file().parent / "proxy_service.json"


def _get_service_pid() -> int | None:
    """Return PID of the active `opencode-cli.exe serve --service` process, if any."""
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='opencode-cli.exe'\" | "
            "Where-Object { $_.CommandLine -like '*serve*' -and $_.CommandLine -like '*--service*' } | "
            "Select-Object -First 1 -ExpandProperty ProcessId"
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=6, creationflags=flags)
        txt = res.stdout.strip()
        return int(txt) if txt.isdigit() else None
    except Exception:
        return None


def _has_unproxied_desktop(port: int) -> bool:
    """True if OpenCode.exe main process is running without Smart Lane --proxy-server."""
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='OpenCode.exe'\" | "
            "Where-Object { $_.CommandLine -notlike '*--type=*' } | "
            "Select-Object -ExpandProperty CommandLine"
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=6, creationflags=flags)
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        if not lines:
            return False
        marker = f"--proxy-server=http://127.0.0.1:{port}"
        return any((marker not in line) or ("<-loopback>" in line) for line in lines)
    except Exception:
        return False


def _save_proxied_service_pid(pid: int | None) -> None:
    marker = _get_proxy_marker_file()
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"pid": pid, "ts": int(time.time())}), encoding="utf-8")
    except Exception:
        pass


def _is_service_using_our_proxy(svc_pid: int | None, proxy_port: int = core.DEFAULT_PROXY_PORT) -> bool:
    if not svc_pid:
        return False
    marker = _get_proxy_marker_file()
    if marker.is_file():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            if data.get("pid") == svc_pid:
                return True
        except Exception:
            pass
    # Also trust services spawned directly by a proxied OpenCode.exe parent
    try:
        ps = (
            f"$svc = Get-CimInstance Win32_Process -Filter \"ProcessId={svc_pid}\"; "
            "if ($svc -and $svc.ParentProcessId) { "
            "$p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($svc.ParentProcessId)\"; "
            "if ($p) { $p.CommandLine } }"
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=6, creationflags=flags)
        return f"--proxy-server=http://127.0.0.1:{proxy_port}" in res.stdout
    except Exception:
        return False


def ensure_service_running() -> bool:
    """Ensure Smart Lane proxy and OpenCode background service are running WITH proxy env."""
    proxy_port = core.DEFAULT_PROXY_PORT
    proxy_ok = ensure_lane_proxy_running(proxy_port)
    cli = find_opencode_cli()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    env = zen_lane.prepare_environment(proxy_port) if proxy_ok else os.environ.copy()

    try:
        svc_pid = _get_service_pid()
        res = subprocess.run([cli, "service", "status"], capture_output=True, text=True, timeout=10, env=env, creationflags=flags)
        running_http = res.returncode == 0 and "http://" in res.stdout

        if running_http and svc_pid and _is_service_using_our_proxy(svc_pid):
            return True

        restarted_desktop = False
        if running_http and svc_pid and not _is_service_using_our_proxy(svc_pid):
            print("  Detected OpenCode service running without Smart Lane proxy — restarting through WARP...")
            if _has_unproxied_desktop(proxy_port):
                print("  Closing unproxied OpenCode Desktop window cleanly before restarting service...")
                subprocess.run(["taskkill", "/F", "/IM", "OpenCode.exe"], capture_output=True, text=True, timeout=10, creationflags=flags)
                restarted_desktop = True
                time.sleep(1.0)
            subprocess.run([cli, "service", "stop"], capture_output=True, text=True, timeout=15, env=env, creationflags=flags)
            for _ in range(10):
                if not _get_service_pid():
                    break
                time.sleep(0.5)
        elif not running_http:
            print("  OpenCode service is stopped. Starting background service with Smart Lane proxy...")

        start_res = subprocess.run([cli, "service", "start"], capture_output=True, text=True, timeout=20, env=env, creationflags=flags)
        if start_res.returncode == 0:
            time.sleep(2)
            _save_proxied_service_pid(_get_service_pid())
            if restarted_desktop:
                launcher = SCRIPT_DIR / "desktop_launcher.py"
                if launcher.is_file():
                    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
                        subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
                    ) if os.name == "nt" else 0
                    subprocess.Popen(
                        [sys.executable, str(launcher)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        creationflags=creationflags,
                        close_fds=True,
                    )
                    print("  Relaunched OpenCode Desktop with Smart Lane proxy.")
            return True
        print(f"  Warning: 'service start' exited {start_res.returncode}: {(start_res.stdout + start_res.stderr).strip()}")
    except Exception as e:
        print(f"  Warning: failed checking/starting service: {e}")
    return False


def run_cli_api(method: str, path: str, data: dict | None = None, timeout: int = 35) -> tuple[int, dict]:
    """Makes a request to the local OpenCode service via `opencode-cli api`."""
    cli = find_opencode_cli()
    cmd = [cli, "api", method, path]
    if data is not None:
        cmd.extend(["-d", json.dumps(data)])

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    stdout = proc.stdout.strip()
    if not stdout:
        if proc.stderr.strip():
            return proc.returncode, {"error": proc.stderr.strip()}
        return proc.returncode, {}

    try:
        return proc.returncode, json.loads(stdout)
    except json.JSONDecodeError:
        return proc.returncode, {"raw": stdout}


def get_latest_session_id() -> str:
    """Finds the most recently active session ID."""
    code, res = run_cli_api("GET", "/api/session")
    if code == 0 and "data" in res and res["data"]:
        sessions = res["data"]
        sessions.sort(key=lambda s: s.get("time", {}).get("updated", 0), reverse=True)
        return sessions[0]["id"]
    return ""


def is_quota_error_message(msg: dict) -> tuple[bool, str]:
    """Checks whether a session message object (or active retry state) represents a free-limit / 429 error."""
    err = msg.get("error") or (msg.get("retry") or {}).get("error") or {}
    if not err:
        return False, ""
    err_type = str(err.get("type", ""))
    err_msg = str(err.get("message", ""))
    err_status = err.get("status", 0)
    raw_body = json.dumps(err).lower()

    if err_status == 429 or "free-limit" in err_type.lower() or any(marker in raw_body for marker in QUOTA_MARKERS):
        return True, err_msg or err_type or "Free usage limit reached (429)"
    return False, ""


def wait_for_prompt_outcome(
    session_id: str,
    prompt_msg_id: str | None,
    prompt_timestamp_ms: int,
    wait_seconds: int = 45,
) -> tuple[str, str, dict]:
    """
    Polls the session messages after sending 'continue' until either:
    - ('quota', err_msg, msg)
    - ('error', err_msg, msg)
    - ('success', '', assistant_msg)
    - ('pending', '', {})
    """
    deadline = time.time() + wait_seconds
    saw_our_prompt = False

    while time.time() < deadline:
        code, res = run_cli_api("GET", f"/api/session/{session_id}/message")
        if code == 0 and "data" in res:
            messages = res["data"]
            # API returns newest-first; isolate slice from our prompt upward
            recent = []
            for m in messages:
                if prompt_msg_id and m.get("id") == prompt_msg_id:
                    saw_our_prompt = True
                    break
                if m.get("time", {}).get("created", 0) >= (prompt_timestamp_ms - 2000):
                    recent.append(m)

            # Inspect recent messages after our prompt (oldest-to-newest)
            for m in reversed(recent):
                is_quota, quota_text = is_quota_error_message(m)
                if is_quota:
                    return "quota", quota_text, m

                if m.get("type") == "assistant":
                    content = m.get("content") or []
                    finish = m.get("finish") or ""
                    err = m.get("error")
                    retry_info = m.get("retry") or {}
                    retry_err = retry_info.get("error") or {}
                    if err:
                        return "error", str(err.get("message") or err), m
                    if retry_err and retry_info.get("attempt", 0) >= 3:
                        return "error", str(retry_err.get("message") or retry_err), m
                    if content or (finish and finish != "error"):
                        return "success", "", m

                if m.get("type") == "idle":
                    outcome = m.get("outcome", "")
                    if outcome == "failed":
                        err = m.get("error") or {}
                        return "error", str(err.get("message") or "Turn failed"), m
                    if outcome in ("completed", "succeeded"):
                        return "success", "", m

        time.sleep(1.5)

    return ("pending", "Timed out waiting for response", {}) if saw_our_prompt else ("pending", "Prompt state unknown", {})


def undo_message(session_id: str, message_id: str) -> bool:
    """
    Reverts the session back to just before `message_id` and commits the revert,
    removing the failed 'continue' prompt and its 429 error reply cleanly.
    """
    if not message_id:
        return False

    # Interrupt first in case the runner is still draining, then retry briefly if session is busy
    for attempt in range(6):
        run_cli_api("POST", f"/api/session/{session_id}/interrupt")
        time.sleep(0.5 if attempt == 0 else 0.8)

        code, stage_res = run_cli_api(
            "POST",
            f"/api/session/{session_id}/revert/stage",
            data={"messageID": message_id, "files": False},
        )
        if code == 0:
            break
        if stage_res.get("_tag") == "SessionBusyError" and attempt < 5:
            continue
        print(f"  Warning: revert/stage failed (code {code}): {stage_res}")
        return False

    code2, commit_res = run_cli_api("POST", f"/api/session/{session_id}/revert/commit")
    if code2 != 0:
        print(f"  Warning: revert/commit failed (code {code2}): {commit_res}")
        return False

    print(f"  [UNDONE] Reverted & removed failed 'continue' message ({message_id}).")
    return True


def auto_continue_loop(session_id: str | None = None, max_cycles: int = 15) -> bool:
    """
    Continually:
    1. Ensures OpenCode background service is running
    2. Sends 'continue' to the session
    3. Waits for the response; if quota wall hit:
       - Undoes the 'continue' message so the chat stays clean
       - Rotates Cloudflare WARP IPv6 to a fresh /64 subnet
       - Repeats until the quota message is gone and the model resumes work
    """
    ensure_service_running()

    if not session_id:
        session_id = get_latest_session_id()
    if not session_id:
        print("Error: No OpenCode sessions found. Pass a session_id explicitly.")
        return False

    print("=== OpenCode Auto-Continue & Unlimit Loop ===")
    print(f"Target Session: {session_id}")
    print(f"CLI Path: {find_opencode_cli()}")
    print(f"Current IPv6: {core.get_current_ipv6() or 'Unknown'}")
    print("=" * 45)

    core.set_auto_continue_active(True)
    try:
        for cycle in range(1, max_cycles + 1):
            core.set_auto_continue_active(True)  # Refresh marker timestamp
            print(f"\n[Cycle {cycle}/{max_cycles}] Sending 'continue' prompt to session {session_id}...")
            prompt_time_ms = int(time.time() * 1000)
            code, prompt_res = run_cli_api("POST", f"/api/session/{session_id}/prompt", data={"text": "continue"})

            prompt_msg_id = (prompt_res.get("data") or {}).get("id")
            if code != 0 or not prompt_msg_id:
                print(f"  Warning: prompt call returned code {code}: {prompt_res}")

            print(f"  Prompt sent (ID: {prompt_msg_id or 'unknown'}). Waiting for outcome...")
            status, detail, msg = wait_for_prompt_outcome(session_id, prompt_msg_id, prompt_time_ms, wait_seconds=45)

            if status == "quota":
                print(f"  [LIMIT HIT] Detected quota wall: '{detail}'")
                if prompt_msg_id:
                    undo_message(session_id, prompt_msg_id)

                print("  Rotating Cloudflare WARP /64 subnet...")
                success, old_v6, new_v6 = core.execute_hop_cycle(max_retries=6)
                if success:
                    print(f"  [ROTATED] Successfully switched IPv6: {old_v6} -> {new_v6}")
                else:
                    print(f"  [WARNING] Hop cycle finished with IPv6: {new_v6}")

                print("  Waiting 5 seconds for network routes to settle...")
                time.sleep(5)
                continue

            if status == "error":
                print(f"  [ERROR] Non-quota error received: {detail}")
                if "ECONNRESET" in detail or "socket" in detail.lower() or "network" in detail.lower():
                    if prompt_msg_id:
                        undo_message(session_id, prompt_msg_id)
                    print("  Transient network error after route switch — retrying...")
                    time.sleep(3)
                    continue
                return False

            if status == "success":
                print("\n" + "=" * 45)
                print("[SUCCESS] Quota message is GONE! Work has resumed successfully.")
                msg_type = msg.get("type", "unknown")
                msg_finish = msg.get("finish", "in-progress")
                print(f"Latest Message Type: {msg_type}, Finish: {msg_finish}")
                for c in msg.get("content", []):
                    c_type = c.get("type", "")
                    if c_type == "reasoning":
                        print(f"Reasoning excerpt: {c.get('text', '')[:200]}...")
                    elif c_type == "text":
                        print(f"Text: {c.get('text', '')[:200]}...")
                    elif c_type == "tool":
                        print(f"Tool executed: {c.get('name', '')}")
                print("=" * 45)
                return True

            print(f"  [PENDING] {detail} — undoing stalled prompt before retrying...")
            if prompt_msg_id:
                undo_message(session_id, prompt_msg_id)
            time.sleep(3)

        print(f"\n[STOPPED] Reached maximum cycles ({max_cycles}) while quota wall persisted.")
        return False
    finally:
        core.set_auto_continue_active(False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Opencode Unlimited Auto-Continue Loop")
    parser.add_argument("session_id", nargs="?", default=None, help="Target session ID")
    parser.add_argument("--max-cycles", type=int, default=15, help="Max retry cycles before giving up")
    args = parser.parse_args()

    ok = auto_continue_loop(args.session_id, max_cycles=args.max_cycles)
    sys.exit(0 if ok else 1)
