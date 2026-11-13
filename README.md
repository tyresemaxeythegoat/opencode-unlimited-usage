# Opencode Unlimited Usage

Bypass OpenCode's free model daily usage wall on **Windows (Native — No WSL Required)** and **Linux / WSL2** using automated Cloudflare WARP IPv6 `/64` + Anycast edge rotation, OpenCode Desktop Smart Lane routing, `opencode-continue` auto-retry/undo, and optional OpenCode-only `WarpProxy` isolation.

Forked from [ElectronBreach/opencode-unlimited-usage](https://github.com/ElectronBreach/opencode-unlimited-usage) with full native Windows CLI & Desktop support, automated `opencode-continue` session recovery, and isolated OpenCode-only `WarpProxy` mode so WARP rotations never interrupt background apps on your PC.

## What actually happens (the short version)

Opencode's free tier isn't keyed to your account. It's keyed to what their server *sees* on the other end:

- your IPv6 `/64` block (what Cloudflare WARP assigns you)
- which Cloudflare edge node your requests land on

Burn through your messages and that combo gets walled for the day. This tool rotates both automatically:

- **Every launch** picks a fresh Cloudflare edge from the live `AAAA` pool (`opencode.ai` / `api.opencode.ai`) and generates a fresh device/machine ID.
- **When a quota wall hits**, the background guard (or `opencode-continue`) blacklists the burned `/64`, re-registers Cloudflare WARP for a brand new `/64`, verifies it isn't on the lifetime blacklist (retrying up to 8 times), and resumes cleanly in ~10–15 seconds.
- **On Windows**, Smart Lane (`lane_proxy.py`) can also tunnel OpenCode exclusively through Cloudflare WARP's local SOCKS5 `WarpProxy` (`127.0.0.1:40000`) while leaving the rest of Windows on your normal connection — failing closed (`502`) instead of leaking your ISP IP if WARP is disconnected.

---

## Install

### Windows (Native — No WSL Required)

**Requirements:**
- Windows 10 or 11 (64-bit)
- Python 3.8+ (with `python.exe` and `pythonw.exe` in `PATH`)
- Cloudflare WARP (`warp-cli.exe` — the installer can install it via `winget` if missing)
- OpenCode CLI and/or OpenCode Desktop

**Steps:**

```powershell
git clone https://github.com/tyresemaxeythegoat/opencode-unlimited-usage.git
cd opencode-unlimited-usage
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Or double-click **`install.bat`** inside the cloned folder. Close and reopen your terminal afterward so `PATH` updates take effect. See [README_WINDOWS.md](README_WINDOWS.md) for full Windows details.

### Linux & WSL2 (Bash)

**Requirements:**
- Linux x86_64 (native or WSL2 with systemd enabled)
- `sudo` access for the install
- `python3`

```bash
curl -fsSL https://raw.githubusercontent.com/tyresemaxeythegoat/opencode-unlimited-usage/main/install.sh | bash
```

Close and reopen your terminal after install (so `PATH` picks things up).

---

## How to Use It

### Windows

| Command / Shortcut | What it does |
|---|---|
| `opencode-desktop` or **`OpenCode (Unlimited)`** shortcut | Launches OpenCode Desktop through the Smart Lane proxy (`127.0.0.1:58245`) with loopback bypass |
| `opencode` | Launches OpenCode CLI wrapped in Smart Lane with randomized edge + device ID |
| `opencode-continue [session_id] [--max-cycles 15]` | Sends `"continue"`, watches for quota errors (`FreeUsageLimitError`, `"you've used today's free messages"`, `429`), automatically interrupts & reverts the failed turn, rotates WARP, and retries |
| `opencode-hop` | Manually rotate to a fresh Cloudflare WARP IPv6 `/64` immediately |
| `opencode-doctor` | Check WARP mode/connection, IPv6 egress, Smart Lane proxy, Zen Guard, and hop stats |

#### Optional: Isolate WARP to OpenCode Only (`WarpProxy` mode on Windows)

To prevent WARP reconnections from interrupting downloads, games, or browsing on your PC, switch WARP to local SOCKS5 `WarpProxy` mode (`127.0.0.1:40000` with `MASQUE`):

```powershell
warp-cli tunnel protocol set MASQUE
warp-cli mode proxy
warp-cli connect
```

Smart Lane (`lane_proxy.py`) automatically detects `WarpProxy` mode and routes **only** proxied OpenCode traffic through `127.0.0.1:40000` (failing closed if WARP is offline). You can also disable the `Cloudflare WARP.exe` tray app from Windows Startup Apps so `warp-svc.exe` runs silently in the background via `warp-cli`.

### Linux & WSL2

| Piece | What it does |
|---|---|
| `zen-lane` | wraps opencode: IPv6-only pin to opencode.ai + random CF edge + random machine-id per launch |
| `zen-guard` | background watcher — sniffs opencode's own log for the wall error, rotates to a fresh `/64` in ~10s |
| `warp-keeper` | root service — keeps WARP connected and re-installs the kill-switch every 45s |
| `zen-hop` | manual "give me a new `/64` right now" button (`opencode-unlimited-hop`) |
| `doctor` | health check (`opencode-unlimited-doctor`) |

Open `opencode` and work normally. If you hit a limit wall, wait ~10 seconds for `zen-guard` to rotate WARP and re-send your message, or run:

```bash
opencode-unlimited-hop     # Rotate immediately
opencode-unlimited-doctor  # Health check
```

## How it works (for people who read code)

- **The wall** is server-side and keyed on `(your /64, CF edge)`. WARP gives you a fresh /64 on every registration, and opencode.ai's AAAA pool gives you several edges to spread across. Both rotate — so the bucket never fills up before you've moved on.
- **zen-lane** creates a mount namespace (`unshare -rm`), binds a generated `/etc/hosts` (opencode.ai → one random IPv6 from the live AAAA pool) and a random `/etc/machine-id` inside it, then execs the real opencode binary. Your actual system files are never touched. Kill the process and the namespace evaporates.
- **zen-guard** tails opencode's own error log (`~/.local/share/opencode/log/opencode.log`) with an offset, so it only reads new bytes. Sees the quota error → pauses the keeper (they'd race otherwise) → deletes the WARP registration → registers fresh → reconnects → resumes the keeper → checks the new /64 against the blacklist → repeats up to 8 times if Cloudflare hands back a burned block. Blacklist is lifetime; if literally everything comes back burned, it recycles the oldest block (these things reset around midnight anyway).
- **warp-keeper** enforces TUN mode every 45s and owns an iptables/ip6tables chain (`OUC_LEAKGUARD`) that allows loopback, LAN, Cloudflare's own control ranges, the WARP interface and established connections — and drops everything else going out. Tunnel dies → the chain is still there → your traffic goes nowhere instead of leaking from your home IP. This is the piece that makes the whole thing safe to run 24/7.
- Docker/containers on the same machine are untouched (the guard only filters the host's OUTPUT chain, FORWARD is left alone).

Everything is plain bash + python3 stdlib. No weird dependencies, no telemetry, no binary blobs.

## FAQ

**Is this safe for my machine?**
Everything runs from `~/.local/share/opencode-unlimited/`. System touches are: two systemd units, one sudoers entry (only for `warp-cli`, nothing else), and the iptables chain. `uninstall.sh` removes all of it cleanly.

**Does it still work if WARP is down?**
No traffic leaves at all — that's by design. The keeper repairs the tunnel in about 15 seconds and you're back.

**My tunnel is up but models still say limit reached.**
Your TUI session picked an edge whose bucket is full for that model. Close and reopen opencode — each launch picks a fresh random edge. The guard handles the /64 side automatically.

**Does this work on Mac / Windows?**
Native Windows 10/11 (CLI & Desktop, no WSL required) is supported via `install.ps1` / `windows/`. Linux and WSL2 (with systemd) are supported via `install.sh` / `scripts/`. Mac is not supported out of the box (would need a launchd service).

**Is it unlimited though?**
For a single human's normal use — yes, in practice. You're not going to hit walls you can't rotate out of. Don't be a robot about it.

## Credit system (Linux installer note)

On Linux, the upstream `install.sh` drops a small agent-rules file (`~/.opencode/AGENTS.md`) from the original author (`@ElectronCursed`), removed cleanly by `uninstall.sh`. The native Windows installer (`install.ps1`) does not modify `~/.opencode/AGENTS.md`.

## Uninstall

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

Or double-click **`uninstall.bat`**.

### Linux & WSL2

```bash
curl -fsSL https://raw.githubusercontent.com/tyresemaxeythegoat/opencode-unlimited-usage/main/uninstall.sh | bash
```

Removes the services, wrappers, startup hooks, and proxy state. Your OpenCode data/sessions are untouched.

## Files

```
install.ps1 / install.bat     — Windows native installer
uninstall.ps1 / uninstall.bat — Windows native uninstaller
README_WINDOWS.md             — Full Windows guide
windows/                      — Windows Smart Lane proxy, Desktop launcher, Zen Guard, Auto-Continue & CLI shims
install.sh / uninstall.sh     — Linux / WSL2 installer and uninstaller
AGENTS.md                     — Upstream Linux agent-rules file
scripts/
  warp-keeper.sh              — Linux root service: TUN enforce + kill-switch repair loop
  zen-lane.sh                 — Linux namespace + IPv6 pin + edge rotation
  zen-guard.sh                — Linux wall watcher + auto /64 rotation
  zen-hop.sh                  — Linux manual identity rotation
  doctor.sh                   — Linux health check
```

MIT license. Original Linux tool by ELECTRONBREACH. Windows port, Desktop Smart Lane, `opencode-continue`, and isolated `WarpProxy` mode maintained in this fork.
