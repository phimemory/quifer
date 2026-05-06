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

ETHERSCAN_API = "https://api.etherscan.io/v2/api"
API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
CACHE_DIR = Path(__file__).parent.parent / "data" / "tx_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Known airdrop contract addresses and their chain IDs.
# chain 1 = Ethereum mainnet, 42161 = Arbitrum One, 10 = Optimism
AIRDROP_CONTRACTS = {
    "arbitrum":  ("0x67a24CE4321aB3aF51c2D0a4801c3E111D88C9d9", 42161),
    "optimism":  ("0xFEb56b15fD44C1F98bFBea5C3a11b71c8EeF9bB", 10),
    "uniswap":   ("0x090D4613473dEE047c3f2706764f49E0821D256e", 1),
}

# Map contract address -> chain ID for quick lookup
CONTRACT_CHAIN: dict[str, int] = {
    addr.lower(): chain_id
    for addr, chain_id in AIRDROP_CONTRACTS.values()
}


def _cache_path(address: str) -> Path:
    return CACHE_DIR / f"{address.lower()}.json"


def _get(params: dict, chain_id: int = 1) -> dict:
    """Etherscan V2 GET with rate-limit retry."""
    params["apikey"] = API_KEY
    params["chainid"] = chain_id
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


def get_normal_txs(address: str, use_cache: bool = True, chain_id: int = 1) -> list[dict]:
    """
    Fetch normal transactions for a wallet address on the given chain.
    Returns list of tx dicts with: blockNumber, timeStamp, from, to, value, gasUsed, isError.
    """
    cache = CACHE_DIR / f"{address.lower()}_{chain_id}.json"
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
    }, chain_id=chain_id)

    txs = data.get("result", [])
    if not isinstance(txs, list):
        txs = []

    if use_cache:
        cache.write_text(json.dumps(txs))

    return txs


def get_erc20_txs(address: str, use_cache: bool = True, chain_id: int = 1) -> list[dict]:
    """Fetch ERC-20 token transfer history for a wallet."""
    cache = CACHE_DIR / f"{address.lower()}_erc20_{chain_id}.json"
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
    }, chain_id=chain_id)

    txs = data.get("result", [])
    if not isinstance(txs, list):
        txs = []

    if use_cache:
        cache.write_text(json.dumps(txs))

    return txs


def get_airdrop_claimers(contract_address: str, use_cache: bool = True) -> list[str]:
    """
    Fetch unique wallet addresses that interacted with an airdrop contract.
    Chain is resolved automatically from CONTRACT_CHAIN; defaults to mainnet.
    """
    chain_id = CONTRACT_CHAIN.get(contract_address.lower(), 1)
    cache = CACHE_DIR / f"claimers_{contract_address.lower()}_{chain_id}.json"
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
    }, chain_id=chain_id)

    txs = data.get("result", [])
    if not isinstance(txs, list):
        return []

    addresses = list({tx["from"].lower() for tx in txs if tx.get("from")})

    if use_cache:
        cache.write_text(json.dumps(addresses))

    return addresses


def fetch_batch(addresses: list[str], delay: float = 0.21, chain_id: int = 1) -> dict[str, list]:
    """
    Fetch normal tx histories for a batch of addresses on the given chain.
    delay=0.21s keeps us under Etherscan's 5 req/sec free tier limit.
    Returns {address: [tx, ...]}
    """
    from tqdm import tqdm
    results = {}
    for addr in tqdm(addresses, desc="fetching txs"):
        try:
            results[addr] = get_normal_txs(addr, chain_id=chain_id)
        except Exception:
            results[addr] = []
        time.sleep(delay)
    return results
