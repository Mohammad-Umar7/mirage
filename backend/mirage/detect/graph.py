"""Fused coordination graph and community detection.

1. Candidate edges = union of each signal's kNN graph (plus accounts that
   share funding ancestry).
2. Every candidate pair gets a similarity on every signal, converted to a
   z-score against the network baseline.
3. Fusion: an edge's weight is the sum of its significant signals; edges
   supported by a single signal are halved (one coincidence is cheap,
   several independent ones are not).
4. Leiden community detection on the weighted graph, then pruning of
   weakly attached members and merging of fragments of the same group.
"""

from __future__ import annotations

import igraph as ig
import leidenalg
import numpy as np

from ..config import DetectorConfig
from ..util import l2_normalize, mean_pairwise_cosine
from .knn import knn
from .signals import DENSE_SIGNALS, SIGNALS, DenseSignal, FundingSignal

ALPHA = {"timing": 1.0, "content": 0.7, "style": 0.9, "behavior": 0.9, "funding": 1.0}
BIT = {name: 1 << i for i, name in enumerate(SIGNALS)}


def canonical_pairs(I: np.ndarray, J: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    ok = (I >= 0) & (J >= 0) & (I != J)
    a, b = np.minimum(I[ok], J[ok]), np.maximum(I[ok], J[ok])
    key = np.unique(a.astype(np.int64) * n + b)
    return key // n, key % n


def candidate_pairs(dense: dict[str, DenseSignal], funding: FundingSignal, n: int, k: int,
                    rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    Is, Js = [], []
    for sig in dense.values():
        if len(sig.rows) < 3:
            continue
        idx, _ = knn(sig.X, k)
        src = np.repeat(sig.rows, idx.shape[1])
        dst_local = idx.ravel()
        ok = dst_local >= 0
        Is.append(src[ok])
        Js.append(sig.rows[dst_local[ok]])
    fi, fj = funding.candidates(k, rng)
    Is.append(fi)
    Js.append(fj)
    if not Is:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    return canonical_pairs(np.concatenate(Is), np.concatenate(Js), n)


def pair_similarities(dense: dict[str, DenseSignal], funding: FundingSignal, I: np.ndarray,
                      J: np.ndarray) -> dict[str, np.ndarray]:
    sims = {name: sig.pair_sim(I, J) for name, sig in dense.items()}
    sims["funding"] = funding.pair_sim(I, J) if len(I) else np.zeros(0, dtype=np.float32)
    return sims


def fuse(z: dict[str, np.ndarray], cfg: DetectorConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_edges = len(next(iter(z.values()))) if z else 0
    w = np.zeros(n_edges, dtype=np.float32)
    bits = np.zeros(n_edges, dtype=np.uint8)
    n_sig = np.zeros(n_edges, dtype=np.int8)
    span = cfg.z_full - cfg.z_floor
    for name, zs in z.items():
        g = np.clip((np.nan_to_num(zs, nan=-1e9) - cfg.z_floor) / span, 0.0, 1.0)
        w += ALPHA[name] * g
        strong = g >= 0.25
        bits |= np.where(strong, BIT[name], 0).astype(np.uint8)
        n_sig += strong.astype(np.int8)
    w = np.where(n_sig <= 1, cfg.single_signal_factor * w, w).astype(np.float32)
    return w, bits, n_sig


def leiden_communities(n: int, I: np.ndarray, J: np.ndarray, w: np.ndarray, cfg: DetectorConfig
                       ) -> list[np.ndarray]:
    keep = w >= cfg.min_edge_weight
    I, J, w = I[keep], J[keep], w[keep]
    if len(I) == 0:
        return []
    nodes, inv = np.unique(np.concatenate([I, J]), return_inverse=True)
    ci, cj = inv[: len(I)], inv[len(I):]
    g = ig.Graph(n=len(nodes), edges=np.column_stack([ci, cj]).tolist(), directed=False)
    g.es["weight"] = w.astype(float).tolist()
    part = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition, weights="weight",
                                    n_iterations=-1, seed=cfg.seed + 1)
    lab = _prune(np.asarray(part.membership, dtype=np.int64), ci, cj, w)
    return [nodes[local] for local in _groups(lab) if len(local) >= 2]


def _groups(lab: np.ndarray) -> list[np.ndarray]:
    idx = np.flatnonzero(lab >= 0)
    if len(idx) == 0:
        return []
    order = idx[np.argsort(lab[idx], kind="stable")]
    return np.split(order, np.flatnonzero(np.diff(lab[order])) + 1)


def _prune(lab: np.ndarray, ci: np.ndarray, cj: np.ndarray, w: np.ndarray, rounds: int = 2) -> np.ndarray:
    """Drop members that hang on to their group by a thread.

    A member stays if its weighted degree inside the group is at least
    max(0.35, 20% of the group's median internal degree).
    """
    lab = lab.copy()
    for _ in range(rounds):
        same = (lab[ci] == lab[cj]) & (lab[ci] >= 0)
        deg = np.bincount(ci[same], weights=w[same], minlength=len(lab)) + \
            np.bincount(cj[same], weights=w[same], minlength=len(lab))
        changed = False
        for grp in _groups(lab):
            vals = deg[grp]
            cut = max(0.35, 0.2 * float(np.median(vals)))
            weak = grp[vals < cut]
            if len(weak):
                lab[weak] = -1
                changed = True
        if not changed:
            break
    return lab


def consolidate(groups: list[np.ndarray], dense: dict[str, DenseSignal], I: np.ndarray, J: np.ndarray,
                w: np.ndarray, n: int, min_size: int) -> list[np.ndarray]:
    """Merge communities that are fragments of one entity.

    Modularity can split one big, homogeneous group into arbitrary chunks.
    Chunks that are connected and whose centroids agree on at least two
    independent signals are merged back together.
    """
    big = [g for g in groups if len(g) >= min_size]
    small = [g for g in groups if len(g) < min_size]
    if len(big) < 2:
        return groups
    label = np.full(n, -1, dtype=np.int64)
    for gi, g in enumerate(big):
        label[g] = gi
    li, lj = label[I], label[J]
    cross = (li >= 0) & (lj >= 0) & (li != lj)
    linked: set[tuple[int, int]] = set()
    for a, b in zip(li[cross].tolist(), lj[cross].tolist()):
        linked.add((min(a, b), max(a, b)))
    # Only internally cohesive fragments are merged: the centroid of an
    # incoherent group points at the population mean and agrees with
    # everything, so it carries no information.
    centroids: dict[str, dict[int, np.ndarray]] = {}
    for name in DENSE_SIGNALS:
        sig = dense.get(name)
        if sig is None:
            continue
        cents = {}
        for gi, g in enumerate(big):
            V = sig.vectors(g)
            if len(V) >= 3 and mean_pairwise_cosine(V) >= 0.4:
                cents[gi] = l2_normalize(V.mean(axis=0, keepdims=True))[0]
        centroids[name] = cents
    parent = list(range(len(big)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in linked:
        agree = 0
        for cents in centroids.values():
            if a in cents and b in cents and float(cents[a] @ cents[b]) >= 0.85:
                agree += 1
        if agree >= 2:
            parent[find(a)] = find(b)
    merged: dict[int, list[np.ndarray]] = {}
    for gi, g in enumerate(big):
        merged.setdefault(find(gi), []).append(g)
    out = [np.unique(np.concatenate(parts)) for parts in merged.values()]
    return out + small
