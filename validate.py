"""
Validate quifer results against the Hop Protocol Sybil exclusion list.

The Hop list (14k addresses) was used as direct input by the Arbitrum Foundation
for their airdrop Sybil detection. Overlap between quifer clusters and this list
is the closest available ground truth.
"""

import json
import requests
from pathlib import Path

HOP_SYBIL_URL = (
    "https://raw.githubusercontent.com/hop-protocol/hop-airdrop"
    "/master/src/data/eliminatedSybilAttackers.csv"
)
RESULTS_FILE = Path(__file__).parent / "results" / "sybil_report.json"


def load_hop_list() -> set[str]:
    print("fetching hop sybil list...")
    r = requests.get(HOP_SYBIL_URL, timeout=15)
    r.raise_for_status()
    addrs = {line.strip().lower() for line in r.text.splitlines() if line.strip()}
    print(f"  loaded {len(addrs)} addresses")
    return addrs


def load_quifer_results() -> tuple[list[str], list[dict]]:
    clusters = json.loads(RESULTS_FILE.read_text())
    flagged = [addr.lower() for c in clusters for addr in c["members"]]
    return flagged, clusters


def main():
    hop = load_hop_list()
    flagged, clusters = load_quifer_results()

    flagged_set = set(flagged)
    overlap = flagged_set & hop

    print()
    print("=" * 60)
    print("  quifer vs hop sybil list")
    print("=" * 60)
    print(f"  quifer flagged wallets : {len(flagged_set)}")
    print(f"  hop list size          : {len(hop)}")
    print(f"  overlap                : {len(overlap)}")
    if flagged_set:
        pct = len(overlap) / len(flagged_set) * 100
        print(f"  precision (flagged in hop list) : {pct:.1f}%")
    print()

    print("  per-cluster breakdown:")
    for c in clusters:
        members = [m.lower() for m in c["members"]]
        hits = [m for m in members if m in hop]
        pct = len(hits) / len(members) * 100
        print(
            f"  cluster {c['cluster_id']+1:02d}  "
            f"size={c['size']:2d}  sim={c['mean_similarity']:.3f}  "
            f"hop_hits={len(hits)}/{len(members)}  ({pct:.0f}%)"
        )

    print()
    print("  addresses confirmed in hop list:")
    for addr in sorted(overlap):
        print(f"    {addr}")


if __name__ == "__main__":
    main()
