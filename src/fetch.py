"""
Fetch wallet transaction histories from Etherscan.
Returns raw transaction lists ready for fingerprinting.
"""

import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ETHERSCAN_API = "https://api.etherscan.io/api"
API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
CACHE_DIR = Path(__file__).parent.parent / "data" / "tx_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Known airdrop contract addresses to filter transactions by.
# Wallets that interacted with these are candidates for Sybil analysis.
AIRDROP_CONTRACTS = {
    "arbitrum":  "0x67a24CE4321aB3aF51c2D0a4801c3E111D88C9d9",
    "optimism":  "0xFEb56b15fD44C1F98bFBea5C3a11b71c8EeF9bB",
    "uniswap":   "0x090D4613473dEE047c3f2706764f49E0821D256e",
}


def _cache_path(address: str) -> Path:
    return CACHE_DIR / f"{address.lower()}.json"


def _get(params: dict) -> dict:
    """Etherscan GET with rate-limit retry."""
    params["apikey"] = API_KEY
    for attempt in range(3):
        try:
            r = requests.get(ETHERSCAN_API, params=params, timeout=10)
            data = r.json()
            if data.get("status") == "1":
                return data
            if data.get("message") == "NOTOK" and "rate" in data.get("result", "").lower():
                time.sleep(0.25 * (attempt + 1))
                continue
            return data
        except requests.RequestException as e:
            if attempt == 2:
                raise
            time.sleep(1)
    return {"status": "0", "result": []}


def get_normal_txs(address: str, use_cache: bool = True) -> list[dict]:
    """
    Fetch normal (ETH) transactions for a wallet address.
    Returns list of tx dicts with: blockNumber, timeStamp, from, to, value, gasUsed, isError.
    """
    cache = _cache_path(address)
    if use_cache and cache.exists():
        return json.loads(cache.read_text())

    data = _get({
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc",
        "offset": 10000,
        "page": 1,
    })

    txs = data.get("result", [])
    if not isinstance(txs, list):
        txs = []

    if use_cache:
        cache.write_text(json.dumps(txs))

    return txs


def get_erc20_txs(address: str, use_cache: bool = True) -> list[dict]:
    """Fetch ERC-20 token transfer history for a wallet."""
    cache = CACHE_DIR / f"{address.lower()}_erc20.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text())

    data = _get({
        "module": "account",
        "action": "tokentx",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc",
        "page": 1,
        "offset": 10000,
    })

    txs = data.get("result", [])
    if not isinstance(txs, list):
        txs = []

    if use_cache:
        cache.write_text(json.dumps(txs))

    return txs


def get_airdrop_claimers(contract_address: str, use_cache: bool = True) -> list[str]:
    """
    Fetch unique wallet addresses that interacted with an airdrop contract.
    These are the candidate Sybil wallets to fingerprint.
    """
    cache = CACHE_DIR / f"claimers_{contract_address.lower()}.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text())

    data = _get({
        "module": "account",
        "action": "txlist",
        "address": contract_address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc",
        "page": 1,
        "offset": 10000,
    })

    txs = data.get("result", [])
    if not isinstance(txs, list):
        return []

    addresses = list({tx["from"].lower() for tx in txs if tx.get("from")})

    if use_cache:
        cache.write_text(json.dumps(addresses))

    return addresses


def fetch_batch(addresses: list[str], delay: float = 0.21) -> dict[str, list]:
    """
    Fetch normal tx histories for a batch of addresses.
    delay=0.21s keeps us under Etherscan's 5 req/sec free tier limit.
    Returns {address: [tx, ...]}
    """
    from tqdm import tqdm
    results = {}
    for addr in tqdm(addresses, desc="fetching txs"):
        try:
            results[addr] = get_normal_txs(addr)
        except Exception as e:
            results[addr] = []
        time.sleep(delay)
    return results
