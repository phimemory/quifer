"""
Funding source analysis: find operator wallets that appear across many wallets
in the dataset. An external address that received ETH from 5+ wallets is
almost certainly the operator collecting from farms.
"""

from collections import defaultdict


def find_shared_recipients(
    wallet_txs: dict[str, list],
    min_wallets: int = 3,
    max_wallets: int = 30,
) -> list[dict]:
    """
    Find external addresses (not in our dataset) that received ETH from
    multiple wallets. Capped at max_wallets to filter out popular DeFi
    contracts (SushiSwap, 1inch, etc.) which are used by everyone.
    Operator wallets typically fund 5-30 farms, not 100+.
    """
    wallet_set = {addr.lower() for addr in wallet_txs}
    recipient_senders: dict[str, set[str]] = defaultdict(set)

    for addr, txs in wallet_txs.items():
        for tx in txs:
            to = tx.get("to", "").lower()
            value = int(tx.get("value", 0))
            if not to or to == addr.lower() or value == 0:
                continue
            if to not in wallet_set:
                recipient_senders[to].add(addr.lower())

    results = []
    for recipient, senders in recipient_senders.items():
        if min_wallets <= len(senders) <= max_wallets:
            results.append({
                "address": recipient,
                "received_from_count": len(senders),
                "received_from": sorted(senders),
            })

    return sorted(results, key=lambda x: x["received_from_count"], reverse=True)


def find_internal_funders(
    wallet_txs: dict[str, list],
    min_funded: int = 2,
) -> list[dict]:
    """
    Find wallets within our dataset that sent ETH to other wallets in the dataset.
    Catches hub wallets that distribute funds to farms.
    """
    wallet_set = {addr.lower() for addr in wallet_txs}
    funded_by: dict[str, list[str]] = defaultdict(list)

    for addr, txs in wallet_txs.items():
        for tx in txs:
            to = tx.get("to", "").lower()
            value = int(tx.get("value", 0))
            if to in wallet_set and to != addr.lower() and value > 0:
                funded_by[addr.lower()].append(to)

    results = []
    for funder, funded in funded_by.items():
        unique = list(set(funded))
        if len(unique) >= min_funded:
            results.append({
                "funder": funder,
                "funded_count": len(unique),
                "funded_wallets": sorted(unique),
            })

    return sorted(results, key=lambda x: x["funded_count"], reverse=True)
