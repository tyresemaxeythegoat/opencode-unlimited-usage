"""
Opencode Unlimited - Zen Hop for Windows
Manual identity rotation: deletes current WARP registration and reconnects to a fresh /64.
"""

import sys
import os
import time

# Add current dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    find_warp_cli,
    get_current_ipv6,
    normalize_prefix_64,
    execute_hop_cycle,
)


def main():
    warp_bin = find_warp_cli()
    if not warp_bin:
        print("[X] warp-cli.exe not found. Make sure Cloudflare WARP is installed.")
        sys.exit(1)

    print("\n--- Opencode Unlimited: Manual Hop ---")
    old_ip = get_current_ipv6()
    old_prefix = normalize_prefix_64(old_ip) if old_ip else "unknown"
    print(f"Current IPv6: {old_ip or 'None'} (Subnet: {old_prefix}::/64)")

    print("Rotating Cloudflare WARP registration...")
    success, _, new_ip = execute_hop_cycle(max_retries=5)

    if not success or not new_ip:
        print("[X] Rotation failed or WARP did not connect. Please check WARP client status.")
        sys.exit(1)

    new_prefix = normalize_prefix_64(new_ip)
    print(f"New IPv6:     {new_ip} (Subnet: {new_prefix}::/64)")

    if old_prefix != new_prefix:
        print("\n=======================================================")
        print(" [OK] FRESH /64 SUBNET ACQUIRED! Re-send your message.")
        print("=======================================================\n")
        sys.exit(0)
    else:
        print("\n[!] Cloudflare assigned the same subnet block. Run hop again if still walled.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
