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
