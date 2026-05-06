"""
Temporal clustering: detect wallets that interacted with the target contract
in tight time windows. Coordinated claim timing is a strong Sybil signal.
"""

from collections import defaultdict
from datetime import datetime, timezone


def cluster_by_timing(
    wallet_txs: dict[str, list],
    contract_address: str,
    window_seconds: int = 300,
    min_cluster_size: int = 3,
) -> list[dict]:
    """
    Group wallets by when they first called contract_address.
    Returns clusters of wallets that acted within the same time window.
    """
    contract = contract_address.lower()
    claim_times: dict[str, int] = {}

    for addr, txs in wallet_txs.items():
        for tx in sorted(txs, key=lambda t: int(t.get("blockNumber", 0))):
            if tx.get("to", "").lower() == contract:
                ts = int(tx.get("timeStamp", 0))
                if ts > 0:
                    claim_times[addr] = ts
                    break

    if not claim_times:
        return []

    bins: dict[int, list[str]] = defaultdict(list)
    for addr, ts in claim_times.items():
        bins[ts // window_seconds].append(addr)

    clusters = []
    for bin_key, members in bins.items():
        if len(members) >= min_cluster_size:
            ts_start = bin_key * window_seconds
            dt = datetime.fromtimestamp(ts_start, tz=timezone.utc)
            clusters.append({
                "window": dt.strftime("%Y-%m-%d %H:%M UTC"),
                "size": len(members),
                "members": [m.lower() for m in members],
            })

    return sorted(clusters, key=lambda c: c["size"], reverse=True)
