"""Deterministic random streams keyed by name, so components don't interfere."""

from __future__ import annotations

import hashlib

import numpy as np


def _key_int(key) -> int:
    digest = hashlib.blake2b(repr(key).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little")


def child_rng(seed: int, *keys) -> np.random.Generator:
    """A generator derived from (seed, *keys); stable across runs and platforms."""
    entropy = [int(seed) & 0xFFFFFFFF] + [_key_int(k) & 0xFFFFFFFF for k in keys]
    return np.random.default_rng(np.random.SeedSequence(entropy))


def hex_address(rng: np.random.Generator) -> str:
    return "0x" + rng.bytes(20).hex()
