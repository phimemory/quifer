"""
Generate Sybil detection reports from clusters.
Outputs CSV and a terminal summary.
"""

import csv
import json
from pathlib import Path
from datetime import datetime

from cluster import SybilCluster


RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def print_summary(clusters: list[SybilCluster], total_wallets: int):
    print(f"\n{'='*60}")
    print(f"  quifer - Sybil Detection Report")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")
    print(f"  Wallets analyzed:   {total_wallets}")
    print(f"  Clusters found:     {len(clusters)}")
    flagged = sum(len(c) for c in clusters)
    print(f"  Wallets flagged:    {flagged} ({100*flagged/max(total_wallets,1):.1f}%)")
    print(f"{'='*60}\n")

    for i, cluster in enumerate(clusters[:20], 1):
        print(f"  Cluster {i:02d}  size={len(cluster.members)}  "
              f"similarity={cluster.mean_similarity:.3f}")
        print(f"    seed: {cluster.seed}")
        for addr in cluster.members[:5]:
            print(f"      {addr}")
        if len(cluster.members) > 5:
            print(f"      ... and {len(cluster.members)-5} more")
        print()


def print_combined_report(
    total_wallets: int,
    phase_clusters: list[SybilCluster],
    timing_clusters: list[dict],
    shared_recipients: list[dict],
    internal_funders: list[dict],
):
    phase_flagged = {addr.lower() for c in phase_clusters for addr in c.members}
    timing_flagged = {addr for c in timing_clusters for addr in c["members"]}
    recipient_flagged = {addr for r in shared_recipients for addr in r["received_from"]}
    funder_flagged = {addr for f in internal_funders for addr in f["funded_wallets"]}
    all_funding_flagged = recipient_flagged | funder_flagged

    all_flagged = phase_flagged | timing_flagged | all_funding_flagged

    high_confidence = {
        a for a in all_flagged
        if sum([a in phase_flagged, a in timing_flagged, a in all_funding_flagged]) >= 2
    }
    low_confidence = all_flagged - high_confidence

    print(f"\n{'='*60}")
    print(f"  quifer - Combined Signal Report")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")
    print(f"  Wallets analyzed:        {total_wallets}")
    print(f"  [1] Phase clusters:      {len(phase_clusters)} clusters, {len(phase_flagged)} wallets")
    timing_w = len(timing_flagged)
    print(f"  [2] Timing clusters:     {len(timing_clusters)} clusters, {timing_w} wallets")
    fund_w = len(all_funding_flagged)
    print(f"  [3] Shared operator:     {len(shared_recipients)+len(internal_funders)} addresses, {fund_w} wallets")
    print(f"{'='*60}")
    print(f"  High confidence (2+ signals): {len(high_confidence)} wallets")
    print(f"  Low confidence  (1 signal):   {len(low_confidence)} wallets")
    print(f"  Total flagged:                {len(all_flagged)} ({100*len(all_flagged)/max(total_wallets,1):.1f}%)")
    print(f"{'='*60}\n")

    if timing_clusters:
        print("  Timing clusters (wallets that claimed in same 1h window):")
        for c in timing_clusters[:5]:
            print(f"    {c['window']}  size={c['size']}")
            for addr in c["members"][:3]:
                print(f"      {addr}")
            if c["size"] > 3:
                print(f"      ... and {c['size']-3} more")
        print()

    if shared_recipients:
        print("  Shared operator wallets (external address receiving ETH from many wallets):")
        for r in shared_recipients[:5]:
            print(f"    {r['address']}  received from {r['received_from_count']} wallets")
            for addr in r["received_from"][:3]:
                print(f"      {addr}")
            if r["received_from_count"] > 3:
                print(f"      ... and {r['received_from_count']-3} more")
        print()

    if internal_funders:
        print("  Internal funders (wallets in dataset that funded others):")
        for f in internal_funders[:5]:
            print(f"    {f['funder']}  funded {f['funded_count']} wallets")
        print()

    return {
        "high_confidence": sorted(high_confidence),
        "low_confidence": sorted(low_confidence),
        "phase_flagged": sorted(phase_flagged),
        "timing_flagged": sorted(timing_flagged),
        "funding_flagged": sorted(all_funding_flagged),
    }


def save_csv(clusters: list[SybilCluster], name: str = "sybil_report"):
    path = RESULTS_DIR / f"{name}.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["cluster_id", "cluster_size", "mean_similarity",
                         "min_similarity", "seed", "address"])
        for i, cluster in enumerate(clusters):
            for addr in cluster.members:
                writer.writerow([
                    i, len(cluster.members),
                    f"{cluster.mean_similarity:.4f}",
                    f"{cluster.min_similarity:.4f}",
                    cluster.seed, addr,
                ])
    print(f"  Saved: {path}")
    return path


def save_json(clusters: list[SybilCluster], name: str = "sybil_report"):
    path = RESULTS_DIR / f"{name}.json"
    data = [
        {
            "cluster_id": i,
            "size": len(c.members),
            "mean_similarity": round(c.mean_similarity, 4),
            "min_similarity": round(c.min_similarity, 4),
            "seed": c.seed,
            "members": c.members,
        }
        for i, c in enumerate(clusters)
    ]
    path.write_text(json.dumps(data, indent=2))
    print(f"  Saved: {path}")
    return path
