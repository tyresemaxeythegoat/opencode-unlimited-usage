# Opencode Unlimited Usage (Windows Native — No WSL Required)

Bypass OpenCode's free model daily usage wall directly on native **Windows 10/11** without WSL, WSL2, Docker, or Linux VMs.

Supports **OpenCode CLI**, **OpenCode Desktop**, **`opencode-continue`** automated session recovery, and optional **OpenCode-only `WarpProxy` isolation**.

---

## How It Works on Windows

OpenCode's free tier rate limit is server-side and keyed on:
1. Your client **IPv6 `/64` block** (assigned by Cloudflare WARP)
2. Which **Cloudflare Anycast edge node** your connection terminates on

**This Windows suite solves both natively in user space:**
- **Smart Lane Proxy (`lane_proxy.py` + `zen_lane.py`)**: Runs a stdlib HTTP/CONNECT proxy on `127.0.0.1:58245`. Requests to `opencode.ai` and `api.opencode.ai` are pinned to a randomized Cloudflare IPv6 edge from the live `AAAA` pool, while loopback traffic stays local (`NO_PROXY` / Chromium `--proxy-bypass-list`).
- **OpenCode-Only `WarpProxy` Isolation (Optional)**: When Cloudflare WARP is in `mode proxy` (`127.0.0.1:40000` over `MASQUE`), Smart Lane tunnels outbound OpenCode traffic through WARP's local SOCKS5 proxy and fails closed (`502`) if WARP is offline — leaving your browser, games, and background apps completely unaffected during WARP hops.
- **OpenCode Desktop Launcher (`desktop_launcher.py` + `launch_desktop.vbs`)**: Launches `OpenCode.exe` with `--proxy-server=http://127.0.0.1:58245` and explicit local bypasses (`127.0.0.1;localhost;[::1];<local>;<hostname>`), creating an **`OpenCode (Unlimited)`** shortcut on your Desktop and Start Menu.
- **Autonomous Zen Guard (`zen_guard.py`)**: Silently watches `%USERPROFILE%\.local\share\opencode\log\opencode.log` (using incremental byte offsets + cross-process lock files `state.lock` / `hop.lock`). When a quota error appears, it blacklists the current `/64`, re-registers WARP, verifies a fresh `/64` (retrying up to 8 times), and restores `mode warp` or `mode proxy` + `MASQUE`.
- **Auto-Continue & Undo (`auto_continue.py` / `opencode-continue`)**: Sends `"continue"` to your OpenCode session, polls for quota/429 failures (`FreeUsageLimitError`, `"you've used today's free messages"`, or active `retry.error`), interrupts & reverts the failed prompt turn (`revert/stage` + `revert/commit`), rotates WARP, and retries automatically.

---

## Requirements

1. **Windows 10 or 11** (64-bit)
2. **Python 3.8+** (`python.exe` and `pythonw.exe` in `PATH`)
3. **Cloudflare WARP for Windows** (`warp-cli.exe` at `C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe` — `install.ps1` offers to install it via `winget` if missing)
4. **OpenCode CLI and/or OpenCode Desktop**

---

## Installation

Open PowerShell in this repository directory and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Or double-click **`install.bat`**.

### What the Installer Does
1. Verifies Python (`python.exe` / `pythonw.exe`), Cloudflare WARP (`warp-cli.exe`), and OpenCode CLI / Desktop.
2. Copies the Windows runtime scripts and command wrappers into `%LOCALAPPDATA%\opencode-unlimited\`.
3. Adds `%LOCALAPPDATA%\opencode-unlimited\bin` to your User `PATH`.
4. Initializes and connects Cloudflare WARP (`registration new`, `mode warp`, `connect`).
5. Registers `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\opencode-unlimited-guard.vbs` and starts `zen_guard.py` silently via `pythonw.exe`.
6. If OpenCode Desktop is installed, runs `setup_desktop_shortcuts.ps1` to create **`OpenCode (Unlimited)`** shortcuts on the Desktop and Start Menu.
7. Runs `opencode-doctor` diagnostics.

> **Note**: Close and reopen any existing PowerShell / CMD / Terminal windows so User `PATH` updates take effect.

---

## How to Use It

### OpenCode Desktop
Launch OpenCode Desktop using either:
- **`OpenCode (Unlimited)`** shortcut on your Desktop or Start Menu
- Terminal command:

```powershell
opencode-desktop
```

Both route `OpenCode.exe` through the local Smart Lane proxy (`127.0.0.1:58245`).

### OpenCode CLI
Run from any terminal (PowerShell, CMD, Git Bash, Windows Terminal):

```powershell
opencode
```

### Auto-Continue on Free Usage Limits (`opencode-continue`)
When an agent run stops due to a free usage wall, let `opencode-continue` automatically rotate WARP, undo the failed `"continue"` message, and retry:

```powershell
opencode-continue
```

Or target a specific session ID and max retry cycle count (defaults to the most recently updated session and `--max-cycles 15`):

```powershell
opencode-continue ses_xxxxxxxxxxxxxxxxxxxx --max-cycles 15
```

`opencode-continue` also verifies that OpenCode's background service (`opencode-cli.exe`) and Desktop app are running through the Smart Lane proxy, restarting them through Smart Lane if they were started unproxied.

### Manual Rotation (`opencode-hop`)
Rotate to a fresh Cloudflare WARP identity and `/64` subnet on demand:

```powershell
opencode-hop
```

### Health Check (`opencode-doctor`)
Inspect WARP mode/connection status, egress IPv6 block, Smart Lane proxy health, Zen Guard daemon status, and rotation history:

```powershell
opencode-doctor
```

---

## Optional: Isolated OpenCode-Only Mode (`WarpProxy` + Lightweight Headless WARP)

By default, WARP runs in full-tunnel `mode warp`. If you want **only OpenCode** to use WARP so reconnects never disturb your browser, calls, or downloads:

1. Switch Cloudflare WARP to `MASQUE` + local SOCKS5 `WarpProxy` mode (`127.0.0.1:40000`):

```powershell
warp-cli tunnel protocol set MASQUE
warp-cli mode proxy
warp-cli connect
```

2. Verify with `opencode-doctor`: it should report `Isolated WarpProxy on 127.0.0.1:40000 - OpenCode only`. `zen_hop.py` and `zen_guard.py` automatically preserve `MASQUE` and `mode proxy` on every rotation.
3. *(Optional)* To run WARP without the tray GUI app, disable **Cloudflare WARP** (`Cloudflare WARP.exe`) in Windows **Task Manager -> Startup apps**; the Windows **Cloudflare WARP** service (`warp-svc.exe`) remains running in the background and is controlled directly by `warp-cli.exe`.

---

## File Structure

```
opencode-unlimited-usage/
├── install.ps1                  # Windows PowerShell installer
├── install.bat                  # Double-clickable Windows batch installer
├── uninstall.ps1                # Windows PowerShell uninstaller
├── uninstall.bat                # Double-clickable Windows batch uninstaller
├── README_WINDOWS.md            # This guide
└── windows/
    ├── core.py                  # Core engine: WARP CLI runner, SOCKS5/IPv6 check, locks, blacklist state
    ├── lane_proxy.py            # Smart Lane IPv6-pinning HTTP/CONNECT proxy (routes via WarpProxy if active)
    ├── zen_lane.py              # CLI wrapper: embedded/shared Smart Lane proxy + randomized device identity
    ├── zen_guard.py             # Background log watcher + automatic WARP rotation
    ├── zen_hop.py               # Manual WARP rotation CLI
    ├── auto_continue.py         # Automated session retry, quota/429 detection, and revert loop
    ├── doctor.py                # Comprehensive diagnostics & health check
    ├── warp_keeper.py           # Tunnel watchdog loop
    ├── desktop_launcher.py      # OpenCode Desktop proxy launcher
    ├── launch_desktop.vbs       # Windowless VBScript runner for OpenCode (Unlimited) shortcut
    ├── setup_desktop_shortcuts.ps1 # Creates OpenCode (Unlimited) Desktop/Start Menu shortcuts
    └── bin/
        ├── opencode.cmd / .ps1          # opencode CLI launcher
        ├── opencode-desktop.cmd / .ps1  # opencode-desktop app launcher
        ├── opencode-continue.cmd / .ps1 # opencode-continue auto-retry CLI
        ├── opencode-hop.cmd / .ps1      # opencode-hop manual rotation CLI
        └── opencode-doctor.cmd / .ps1   # opencode-doctor diagnostics CLI
```

---

## Uninstallation

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

Or double-click **`uninstall.bat`**. This:
1. Removes the `OpenCode (Unlimited)` Desktop and Start Menu shortcuts.
2. Stops background processes (`zen_guard.py`, `lane_proxy.py`, `warp_keeper.py`).
3. Removes `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\opencode-unlimited-guard.vbs`.
4. Cleans `%LOCALAPPDATA%\opencode-unlimited\bin` from your User `PATH`.
5. Removes `%LOCALAPPDATA%\opencode-unlimited`.
