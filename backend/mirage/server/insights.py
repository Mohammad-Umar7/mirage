"""Data behind the evidence panel and the Pulse Terrain view.

Everything here is derived from public data and detector output.
"""

from __future__ import annotations

import numpy as np

from ..detect.types import ORGANIC, SWARM, Cluster, DetectionResult
from ..network import NetworkState

HALF_HOUR_BINS = 2  # the feature store bins at 15 minutes


def _short(addr: str) -> str:
    return f"{addr[:6]}…{addr[-4:]}" if len(addr) > 12 else addr


def _half_hours(A: np.ndarray, hours: int) -> np.ndarray:
    """(n, hours*4) 15-min counts → (n, hours*2) 30-min counts."""
    take = A[:, -hours * 4:]
    return take.reshape(take.shape[0], -1, HALF_HOUR_BINS).sum(axis=2)


def _background_pool(result: DetectionResult, activity: np.ndarray) -> np.ndarray:
    ac = result.account_cluster
    n = min(len(ac), len(activity))
    return np.flatnonzero((ac[:n] < 0) & (activity[:n] > 0))


def activity_timeline(cluster: Cluster, engine, result: DetectionResult, hours: int = 48) -> dict:
    store = engine.store
    A = store.timing_matrix()
    H = _half_hours(A, hours)
    members = cluster.members[cluster.members < len(H)]
    pool = _background_pool(result, A.sum(axis=1))
    rng = np.random.default_rng(cluster.id)
    if len(pool) > 800:
        pool = rng.choice(pool, 800, replace=False)
    return {
        "bin_minutes": 30,
        "end": store.now,
        "cluster": H[members].mean(axis=0).round(4).tolist() if len(members) else [],
        "baseline": H[pool].mean(axis=0).round(4).tolist() if len(pool) else [],
    }


def funding_tree(cluster: Cluster, engine, net: NetworkState, max_accounts: int = 40) -> dict:
    """Sampled funding ancestry of the cluster, collapsed into a small tree."""
    store = engine.store
    fg = store.funding
    rng = np.random.default_rng(cluster.id + 17)
    members = cluster.members
    sample = members if len(members) <= max_accounts else np.sort(rng.choice(members, max_accounts, replace=False))
    nodes: dict[int, dict] = {}
    edges: set[tuple[int, int]] = set()
    for a in sample.tolist():
        w = int(store.wallet[a])
        nodes[w] = {"id": w, "kind": "account", "label": net.handles[a], "depth": 0}
        cur, depth = w, 0
        while depth < fg.k:
            funders = fg.first_funders.get(cur)
            if not funders:
                break
            f = int(funders[0][1])
            edges.add((f, cur))
            depth += 1
            if fg.is_hub(f):
                label = net.wallet_label[f] or _short(net.wallet_addr[f])
                prev = nodes.get(f, {"depth": 0})
                nodes[f] = {"id": f, "kind": "hub", "label": label.replace("Exchange · ", ""),
                            "depth": max(depth, prev["depth"])}
                break
            node = nodes.setdefault(f, {"id": f, "kind": "wallet", "label": _short(net.wallet_addr[f]), "depth": depth})
            node["depth"] = max(node["depth"], depth)
            cur = f
    funded = {d for _, d in edges}
    for w, node in nodes.items():
        if node["kind"] == "wallet" and w not in funded:
            node["kind"] = "root"
    roots = sum(1 for n in nodes.values() if n["kind"] in ("root", "hub"))
    return {"nodes": list(nodes.values()), "edges": [[s, d] for s, d in edges], "accounts": len(sample),
            "roots": roots, "max_depth": max((n["depth"] for n in nodes.values()), default=0)}


def similarity_heatmap(cluster: Cluster, engine, result: DetectionResult, k: int = 10) -> dict:
    """Average cross-signal similarity: k cluster members vs k typical accounts."""
    from ..detect.signals import DenseSignal  # noqa: F401  (type only)

    rng = np.random.default_rng(cluster.id + 31)
    members = cluster.members
    inside = members if len(members) <= k else rng.choice(members, k, replace=False)
    store = engine.store
    activity = store.act[: store.n].sum(axis=1)
    pool = _background_pool(result, activity)
    outside = pool if len(pool) <= k else rng.choice(pool, k, replace=False)
    accounts = np.concatenate([inside, outside]).astype(np.int64)
    signals = getattr(engine, "last_signals", None) or {}
    m = len(accounts)
    total = np.zeros((m, m))
    count = np.zeros((m, m))
    for sig in signals.values():
        pos = sig.pos[accounts]
        ok = pos >= 0
        if ok.sum() < 2:
            continue
        V = np.zeros((m, sig.X.shape[1]), dtype=np.float32)
        V[ok] = sig.X[pos[ok]]
        S = V @ V.T
        mask = np.outer(ok, ok)
        total += np.where(mask, S, 0.0)
        count += mask
    values = np.where(count > 0, total / np.maximum(count, 1), 0.0)
    np.fill_diagonal(values, 1.0)
    return {"size": m, "split": int(len(inside)), "values": np.clip(values, -1, 1).round(3).ravel().tolist()}


def sample_posts(cluster: Cluster, net: NetworkState, k: int = 6) -> list[dict]:
    rng = np.random.default_rng(cluster.id + 7)
    members = set(cluster.members.tolist())
    out: list[dict] = []
    authors = net.post_author.a
    for pid in range(net.n_posts - 1, max(-1, net.n_posts - 20000), -1):
        a = int(authors[pid])
        if a in members:
            out.append({"handle": net.handles[a], "text": net.post_text[pid], "t": float(net.post_t[pid])})
            members.discard(a)
            if len(out) >= k * 3:
                break
    if len(out) > k:
        out = [out[i] for i in sorted(rng.choice(len(out), k, replace=False))]
    return out


def evidence_detail(cluster: Cluster, engine, result: DetectionResult, net: NetworkState) -> dict:
    return {
        "type": "evidence",
        "cluster": cluster.to_dict(with_members=False),
        "timeline": activity_timeline(cluster, engine, result),
        "funding": funding_tree(cluster, engine, net),
        "heatmap": similarity_heatmap(cluster, engine, result),
        "posts": sample_posts(cluster, net),
    }


def terrain(engine, result: DetectionResult, hours: int = 72, background_lanes: int = 30) -> dict:
    """Lanes of mean activity per account in 30-minute bins.

    Detected swarm / organic clusters get their own lane; everyone else is
    split into deterministic background lanes of ordinary accounts.
    """
    store = engine.store
    A = store.timing_matrix()
    H = _half_hours(A, hours)
    activity = A.sum(axis=1)
    lanes = []
    shown = [c for c in result.clusters if c.verdict in (SWARM, ORGANIC)]
    shown.sort(key=lambda c: (c.verdict != SWARM, -c.size))
    for c in shown[:6]:
        mem = c.members[c.members < len(H)]
        if len(mem):
            lanes.append({"kind": "swarm" if c.verdict == SWARM else "organic", "cluster": c.id, "size": int(len(mem)),
                          "values": H[mem].mean(axis=0)})
    pool = _background_pool(result, activity)
    bg = []
    for b in range(background_lanes):
        mem = pool[pool % background_lanes == b][:250]
        if len(mem):
            bg.append({"kind": "normal", "cluster": -1, "size": int(len(mem)), "values": H[mem].mean(axis=0)})
    ref = np.percentile(np.concatenate([x["values"] for x in bg]), 99) if bg else 1.0
    scale = 1.0 / max(ref * 2.5, 1e-6)
    ordered = bg[: len(bg) // 2] + lanes + bg[len(bg) // 2:]
    for lane in ordered:
        lane["values"] = np.clip(lane["values"] * scale, 0, 4).round(3).tolist()
    return {"type": "terrain", "bin_minutes": 30, "end": store.now, "lanes": ordered}
