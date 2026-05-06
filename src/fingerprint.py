"""
Build Helix phase fingerprints from wallet transaction sequences.

Each transaction is encoded as a fixed-size feature vector and fed into
a HelixNeuronCell. The resulting phase state is the wallet's fingerprint.
Two wallets with similar transaction SEQUENCES (not just similar stats)
will have similar phase states. Order matters — that is the Helix advantage
over simple feature vectors.
"""

import sys
import math
from pathlib import Path

import torch

# helix package lives at Desktop/helix/ — add Desktop to sys.path
DESKTOP = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(DESKTOP))
from helix import HelixNeuronCell

# Feature dimension per transaction
TX_FEATURES = 12


def encode_tx(tx: dict, address: str) -> torch.Tensor:
    """
    Encode a single transaction into a normalized feature vector.

    Features (12 dims):
      0  is_outgoing         — 1 if wallet sent, 0 if received
      1  log_value           — log1p(ETH value in wei) normalized to [0,1]
      2  log_gas_used        — log1p(gasUsed) normalized to [0,1]
      3  log_gas_price       — log1p(gasPrice) normalized to [0,1]
      4  is_contract_call    — 1 if input data != '0x'
      5  is_error            — 1 if tx failed
      6  hour_of_day         — [0,1] (0=midnight, 1=23:00)
      7  day_of_week         — [0,1] (0=Mon, 1=Sun)
      8  log_block           — relative block position [0,1] over 20M block range
      9  nonce_bucket        — log1p(nonce)/10 clamped to [0,1]
     10  to_is_contract      — proxy: 1 if 'to' address looks like contract (heuristic)
     11  value_bucket        — 0=dust(<1k wei), 0.33=small, 0.66=medium, 1.0=large
    """
    addr = address.lower()
    sender = tx.get("from", "").lower()

    is_outgoing = 1.0 if sender == addr else 0.0

    try:
        value = int(tx.get("value", 0))
    except (ValueError, TypeError):
        value = 0
    log_val = math.log1p(value) / 50.0  # log1p(1e18 ETH) ≈ 41.4 → /50 ≈ 0.83

    try:
        gas_used = int(tx.get("gasUsed", 21000))
    except (ValueError, TypeError):
        gas_used = 21000
    log_gas = math.log1p(gas_used) / 15.0  # log1p(1e6) ≈ 13.8 → /15 ≈ 0.92

    try:
        gas_price = int(tx.get("gasPrice", 1_000_000_000))
    except (ValueError, TypeError):
        gas_price = 1_000_000_000
    log_gp = math.log1p(gas_price) / 30.0

    input_data = tx.get("input", "0x")
    is_contract = 1.0 if (input_data and input_data != "0x") else 0.0

    is_error = float(tx.get("isError", "0") == "1")

    try:
        ts = int(tx.get("timeStamp", 0))
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hour = dt.hour / 23.0
        dow = dt.weekday() / 6.0
    except Exception:
        hour = 0.5
        dow = 0.5

    try:
        block = int(tx.get("blockNumber", 0))
    except (ValueError, TypeError):
        block = 0
    log_block = min(math.log1p(block) / math.log1p(20_000_000), 1.0)

    try:
        nonce = int(tx.get("nonce", 0))
    except (ValueError, TypeError):
        nonce = 0
    nonce_feat = min(math.log1p(nonce) / 10.0, 1.0)

    # Heuristic: contract addresses often have no ETH value in the tx that created them
    to_addr = tx.get("to", "")
    to_is_contract = 1.0 if (is_contract and to_addr) else 0.0

    val_bucket = (
        0.0 if value < 1_000 else
        0.33 if value < 1_000_000_000_000_000 else   # < 0.001 ETH
        0.66 if value < 1_000_000_000_000_000_000 else  # < 1 ETH
        1.0
    )

    feats = [
        is_outgoing, min(log_val, 1.0), min(log_gas, 1.0), min(log_gp, 1.0),
        is_contract, is_error, hour, dow, log_block, nonce_feat,
        to_is_contract, val_bucket,
    ]
    return torch.tensor(feats, dtype=torch.float32)


class WalletFingerprinter:
    """
    Converts a wallet's transaction history into a Helix phase fingerprint.

    The fingerprint is a tensor of shape (hidden_size,) — the accumulated
    phase state after processing every transaction in chronological order.

    Because Helix accumulates phase (not a running average), the ORDER of
    transactions is encoded in the fingerprint. Two wallets that made the
    same transactions in different orders get different fingerprints.
    This is the key advantage over feature vectors.
    """

    def __init__(self, hidden_size: int = 64, harmonics=None):
        harmonics = harmonics or [1, 2, 4, 8]
        self.hidden_size = hidden_size
        self.harmonics = harmonics
        self.cell = HelixNeuronCell(
            input_size=TX_FEATURES,
            hidden_size=hidden_size,
            harmonics=harmonics,
            use_spinor=False,
            quantization_strength=0.125,
            persistence=1.0,
        )
        self.cell.eval()

    @torch.no_grad()
    def fingerprint(self, address: str, txs: list[dict]) -> torch.Tensor | None:
        """
        Build a phase fingerprint from a wallet's transaction list.
        Transactions must be sorted by blockNumber ascending (Etherscan default).

        Returns phase tensor of shape (hidden_size,), or None if no valid txs.
        """
        if not txs:
            return None

        phi = torch.zeros(1, self.hidden_size)
        processed = 0

        for tx in txs:
            try:
                feat = encode_tx(tx, address).unsqueeze(0)  # (1, TX_FEATURES)
                _, phi, _, _, _ = self.cell(feat, phi)
                processed += 1
            except Exception:
                continue

        if processed == 0:
            return None

        return phi.squeeze(0)  # (hidden_size,)

    @torch.no_grad()
    def fingerprint_batch(
        self,
        wallet_txs: dict[str, list[dict]],
    ) -> dict[str, torch.Tensor]:
        """
        Fingerprint a batch of wallets.
        wallet_txs: {address: [tx, ...]}
        Returns {address: phase_tensor} for wallets with at least 1 tx.
        """
        from tqdm import tqdm
        results = {}
        for addr, txs in tqdm(wallet_txs.items(), desc="fingerprinting"):
            phi = self.fingerprint(addr, txs)
            if phi is not None:
                results[addr] = phi
        return results

    def harmonic_features(self, phi: torch.Tensor) -> torch.Tensor:
        """
        Expand a phase tensor into a full harmonic feature vector.
        Shape: (hidden_size * len(harmonics) * 2,)
        This is what you pass to cosine similarity for search.
        """
        parts = []
        for h in self.harmonics:
            parts.append(torch.cos(h * phi))
            parts.append(torch.sin(h * phi))
        return torch.cat(parts)
