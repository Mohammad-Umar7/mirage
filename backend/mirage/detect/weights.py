"""Correlation-weighted voting: accounts that are coordinated share fate.

A flagged cluster of n accounts gets a total voting weight of 1 ("one")
or ln(n) ("log"), split evenly across its members. Every other account
keeps weight 1. The swarm's only advantage - numbers - disappears.
"""

from __future__ import annotations

import math

import numpy as np

from ..network import NetworkState
from .types import SWARM


def cluster_total_weight(size: int, mode: str = "one") -> float:
    if mode == "log":
        return max(1.0, math.log(size)) if size > 0 else 0.0
    return 1.0


def account_weights(n: int, clusters, mode: str = "one", threshold: float = 0.8) -> np.ndarray:
    w = np.ones(n, dtype=np.float64)
    for c in clusters:
        if c.verdict == SWARM and c.confidence >= threshold and c.size > 0:
            w[c.members] = cluster_total_weight(c.size, mode) / c.size
    return w


def tally(net: NetworkState, proposal_id: int, weights: np.ndarray | None = None) -> dict:
    voters, choices, _ = net.votes(proposal_id)
    yes_mask = choices == 1
    out = {"proposal": proposal_id, "n_yes": int(yes_mask.sum()), "n_no": int((~yes_mask).sum())}
    if weights is None:
        out["yes"], out["no"] = float(out["n_yes"]), float(out["n_no"])
    else:
        w = np.ones(len(voters))
        known = voters < len(weights)
        w[known] = weights[voters[known]]
        out["yes"], out["no"] = float(w[yes_mask].sum()), float(w[~yes_mask].sum())
    out["passing"] = out["yes"] > out["no"]
    return out
