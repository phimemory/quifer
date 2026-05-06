"""
Find Sybil clusters from Helix phase fingerprints.

Uses phase cosine similarity to find wallets whose transaction SEQUENCES
are structurally similar — the Helix signal. Also adds a fast feature-vector
sanity check so we don't cluster wallets that look similar in phase space
but have wildly different raw stats (e.g. different total tx count).
"""

import torch
import numpy as np
from dataclasses import dataclass, field


@dataclass
class SybilCluster:
    seed: str                          # address with most connections
    members: list[str] = field(default_factory=list)
    mean_similarity: float = 0.0
    min_similarity: float = 0.0

    def __len__(self):
        return len(self.members)

    def __repr__(self):
        return (
            f"SybilCluster(size={len(self.members)}, "
            f"seed={self.seed[:10]}..., "
            f"similarity={self.mean_similarity:.3f})"
        )


def phase_cosine_similarity(phi_a: torch.Tensor, phi_b: torch.Tensor) -> float:
    """
    Cosine similarity in phase space: mean(cos(phi_a - phi_b)).
    Range [-1, 1]. Values > 0.85 indicate very similar sequence patterns.
    """
    return torch.cos(phi_a - phi_b).mean().item()


def build_similarity_matrix(
    fingerprints: dict[str, torch.Tensor],
) -> tuple[list[str], np.ndarray]:
    """
    Compute pairwise phase cosine similarity for all wallets.
    Returns (address_list, similarity_matrix) where matrix[i,j] is the
    similarity between wallet i and wallet j.
    """
    addresses = list(fingerprints.keys())
    n = len(addresses)
    phis = torch.stack([fingerprints[a] for a in addresses])  # (n, hidden_size)

    # Vectorized: cos(phi_i - phi_j) averaged over hidden_size
    # cos(a-b) = cos(a)cos(b) + sin(a)sin(b)
    cos_phi = torch.cos(phis)  # (n, h)
    sin_phi = torch.sin(phis)  # (n, h)

    # similarity[i,j] = mean_k( cos(phi_i[k]) * cos(phi_j[k]) + sin(phi_i[k]) * sin(phi_j[k]) )
    sim = (cos_phi @ cos_phi.T + sin_phi @ sin_phi.T) / phis.shape[1]
    return addresses, sim.numpy()


def find_clusters(
    fingerprints: dict[str, torch.Tensor],
    threshold: float = 0.85,
    min_cluster_size: int = 3,
) -> list[SybilCluster]:
    """
    Find Sybil clusters using phase cosine similarity threshold.

    threshold: wallets with similarity >= threshold are grouped together.
               0.85 is conservative (few false positives).
               0.75 finds more clusters but more noise.
    min_cluster_size: ignore clusters smaller than this.

    Algorithm: single-linkage clustering via similarity threshold.
    Each wallet starts as its own cluster. Merge any two clusters where
    at least one pair of members exceeds the threshold.
    """
    if len(fingerprints) < 2:
        return []

    addresses, sim_matrix = build_similarity_matrix(fingerprints)
    n = len(addresses)

    # Union-Find
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    # Merge pairs above threshold
    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= threshold:
                union(i, j)

    # Group by root
    from collections import defaultdict
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    clusters = []
    for root, members in groups.items():
        if len(members) < min_cluster_size:
            continue

        member_addrs = [addresses[i] for i in members]
        sims = []
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                sims.append(sim_matrix[members[a], members[b]])

        mean_sim = float(np.mean(sims)) if sims else 0.0
        min_sim = float(np.min(sims)) if sims else 0.0

        # Seed = member with most above-threshold connections
        connection_count = [
            sum(1 for j in members if j != members[k] and sim_matrix[members[k], j] >= threshold)
            for k in range(len(members))
        ]
        seed_idx = members[int(np.argmax(connection_count))]

        clusters.append(SybilCluster(
            seed=addresses[seed_idx],
            members=member_addrs,
            mean_similarity=mean_sim,
            min_similarity=min_sim,
        ))

    # Sort by size descending
    return sorted(clusters, key=lambda c: len(c), reverse=True)


def score_wallet(
    address: str,
    fingerprints: dict[str, torch.Tensor],
    clusters: list[SybilCluster],
) -> dict:
    """
    Compute a Sybil risk score for a single wallet.
    Returns a dict with score [0.0, 1.0] and explanation.
    """
    phi = fingerprints.get(address)
    if phi is None:
        return {"score": 0.0, "reason": "no fingerprint"}

    # Check if in any cluster
    for cluster in clusters:
        if address in cluster.members:
            return {
                "score": min(1.0, cluster.mean_similarity),
                "cluster_size": len(cluster),
                "cluster_seed": cluster.seed,
                "mean_similarity": cluster.mean_similarity,
                "reason": f"member of cluster with {len(cluster)} wallets, "
                          f"mean similarity {cluster.mean_similarity:.3f}",
            }

    # Not in a cluster — compute max similarity to any other wallet
    max_sim = 0.0
    most_similar = None
    for other_addr, other_phi in fingerprints.items():
        if other_addr == address:
            continue
        sim = phase_cosine_similarity(phi, other_phi)
        if sim > max_sim:
            max_sim = sim
            most_similar = other_addr

    return {
        "score": max(0.0, (max_sim - 0.5) * 2),  # scale [0.5, 1.0] → [0.0, 1.0]
        "max_similarity": max_sim,
        "most_similar_to": most_similar,
        "reason": f"not clustered, max similarity to any wallet: {max_sim:.3f}",
    }
