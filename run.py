"""
quifer - Sybil detection pipeline.

Usage:
    # Analyze wallets that interacted with Arbitrum airdrop contract
    python run.py --mode airdrop --contract 0x67a24CE4321aB3aF51c2D0a4801c3E111D88C9d9 --limit 500

    # Analyze a specific list of addresses from a file (one per line)
    python run.py --mode file --input addresses.txt

    # Test with a small set of hardcoded wallets (no API key needed)
    python run.py --mode demo
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fetch import get_airdrop_claimers, fetch_batch
from fingerprint import WalletFingerprinter
from cluster import find_clusters, score_wallet
from report import print_summary, save_csv, save_json


# ------------------------------------------------------------------
# Demo wallets — known Sybil farm from public research
# (Arbitrum airdrop, documented in Nansen/Chainalysis reports)
# These are public blockchain addresses, no PII.
# ------------------------------------------------------------------
DEMO_WALLETS = [
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B",
    "0x1Db3439a222C519ab44bb1144fC28167b4Fa6EE6",
]


def run_demo():
    print("\nquifer demo mode - using 3 wallets (no API key needed)")
    print("In real mode, point --mode airdrop at a real contract address.\n")

    # Simulate transactions (real demo would fetch from Etherscan)
    import torch
    fake_fingerprints = {}
    for i, addr in enumerate(DEMO_WALLETS):
        # Two wallets get similar phase states (simulated Sybil pair)
        if i < 2:
            phi = torch.ones(64) * 3.14 + torch.randn(64) * 0.05
        else:
            phi = torch.randn(64) * 2.0
        fake_fingerprints[addr] = phi

    clusters = find_clusters(fake_fingerprints, threshold=0.85, min_cluster_size=2)
    print_summary(clusters, len(fake_fingerprints))

    for addr in DEMO_WALLETS:
        score = score_wallet(addr, fake_fingerprints, clusters)
        print(f"  {addr[:12]}...  score={score['score']:.3f}  {score['reason']}")

    print("\nRun with --mode airdrop to analyze real on-chain data.")


def run_airdrop(contract: str, limit: int, threshold: float):
    print(f"\nquifer - fetching claimers from {contract}")
    addresses = get_airdrop_claimers(contract)
    if not addresses:
        print("No addresses found. Check your ETHERSCAN_API_KEY in .env")
        return
    addresses = addresses[:limit]
    print(f"  Found {len(addresses)} claimers, analyzing {len(addresses)}")

    wallet_txs = fetch_batch(addresses)
    fingerprinter = WalletFingerprinter(hidden_size=64)
    fingerprints = fingerprinter.fingerprint_batch(wallet_txs)
    print(f"  Fingerprinted {len(fingerprints)} wallets")

    clusters = find_clusters(fingerprints, threshold=threshold)
    print_summary(clusters, len(fingerprints))
    save_csv(clusters)
    save_json(clusters)


def run_file(input_path: str, threshold: float):
    addresses = [l.strip() for l in open(input_path) if l.strip().startswith("0x")]
    print(f"\nquifer - analyzing {len(addresses)} addresses from {input_path}")

    wallet_txs = fetch_batch(addresses)
    fingerprinter = WalletFingerprinter(hidden_size=64)
    fingerprints = fingerprinter.fingerprint_batch(wallet_txs)

    clusters = find_clusters(fingerprints, threshold=threshold)
    print_summary(clusters, len(fingerprints))
    save_csv(clusters)
    save_json(clusters)


def main():
    parser = argparse.ArgumentParser(description="quifer - Sybil detector")
    parser.add_argument("--mode", choices=["demo", "airdrop", "file"], default="demo")
    parser.add_argument("--contract", default="", help="Airdrop contract address")
    parser.add_argument("--input", default="addresses.txt", help="File with addresses")
    parser.add_argument("--limit", type=int, default=500, help="Max wallets to analyze")
    parser.add_argument("--threshold", type=float, default=0.85,
                        help="Similarity threshold for clustering (0.75-0.95)")
    args = parser.parse_args()

    if args.mode == "demo":
        run_demo()
    elif args.mode == "airdrop":
        if not args.contract:
            print("--contract required for airdrop mode")
            sys.exit(1)
        run_airdrop(args.contract, args.limit, args.threshold)
    elif args.mode == "file":
        run_file(args.input, args.threshold)


if __name__ == "__main__":
    main()
