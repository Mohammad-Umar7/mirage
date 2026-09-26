"""Detection engine: public network in, clusters + evidence + vote weights out.

The engine receives a :class:`mirage.network.NetworkState` and nothing
else. It never sees labels, hidden profiles or operator plans.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..config import DetectorConfig
from ..network import NetworkState
from .baseline import Baseline
from .embed import make_embedder
from .evidence import build_evidence
from .features import FeatureStore
from .graph import ALPHA, candidate_pairs, consolidate, fuse, leiden_communities, pair_similarities, refine
from .knn import backend_name
from .scoring import (WEIGHTS, ScoringContext, confidence, group_metrics, level_estimate, remember,
                      session_script, strengths, verdict)
from .signals import FundingSignal, SocialSignal, behavior_signal, content_signal, style_signal, timing_signal
from .tracking import ClusterTracker
from .types import ORGANIC, SWARM, Cluster, DetectionResult
from .weights import account_weights

REF_KEYS = ("sync", "content", "style", "behavior", "follow_density", "fund_shared_frac")
N_RANDOM_PAIRS = 6000
N_RANDOM_GROUPS = 6
RANDOM_GROUP_SIZE = 30

# one shared worker for post embedding (module level so engines stay deep-copyable)
_EMBED_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mirage-embed")

_POOL_LIMIT = None


def _limit_thread_pools() -> None:
    """BLAS and FAISS each spawning a pool per core hurts more than it helps."""
    global _POOL_LIMIT
    if _POOL_LIMIT is None:
        try:
            from threadpoolctl import threadpool_limits

            _POOL_LIMIT = threadpool_limits(limits=8)
        except Exception:  # pragma: no cover - optional dependency
            _POOL_LIMIT = False


def _topk_mask(nodes: np.ndarray, score: np.ndarray, k: int) -> np.ndarray:
    """Mask of edges that are among the top-k (by score) edges of `nodes`."""
    if len(nodes) == 0:
        return np.zeros(0, dtype=bool)
    order = np.lexsort((-score, nodes))
    sn = nodes[order]
    first = np.r_[True, sn[1:] != sn[:-1]]
    start = np.maximum.accumulate(np.where(first, np.arange(len(order)), 0))
    rank = np.arange(len(order)) - start
    out = np.zeros(len(nodes), dtype=bool)
    out[order[rank < k]] = True
    return out


class DetectionEngine:
    def __init__(self, cfg: DetectorConfig | None = None, embedder=None) -> None:
        self.cfg = cfg or DetectorConfig()
        self.embedder = embedder if embedder is not None else make_embedder(self.cfg.embedder)
        self.store = FeatureStore(self.cfg, self.embedder)
        self.base = Baseline(self.cfg.baseline_alpha)
        self.tracker = ClusterTracker()
        self.runs = 0
        self.flagged = np.zeros(0, dtype=bool)
        self.memory: dict[int, tuple[float, dict[str, float]]] = {}
        self.last_signals: dict = {}
        self._n_prev = 0
        self.last: DetectionResult | None = None
        _limit_thread_pools()

    # ------------------------------------------------------------------ run
    def run(self, net: NetworkState) -> DetectionResult:
        cfg = self.cfg
        started = time.perf_counter()
        stages: dict[str, float] = {}
        clock = [time.perf_counter()]

        def mark(name: str) -> None:
            now = time.perf_counter()
            stages[name] = round((now - clock[0]) * 1000.0, 2)
            clock[0] = now

        store = self.store
        store.sync(net)
        n = store.n
        growth = (n - self._n_prev) / self._n_prev if self._n_prev else 0.0
        self._n_prev = n
        alpha = cfg.baseline_alpha * (0.25 if growth > 0.03 else 1.0)
        rng = np.random.default_rng([cfg.seed, self.runs])
        mark("ingest")

        # Embedding new posts (GPU, or its own BLAS work) overlaps with the CPU
        # signals that don't read embeddings; only the content signal waits.
        embed_job = _EMBED_POOL.submit(store.embed_pending, net, cfg.embed_budget)
        base = self.base
        timing = timing_signal(store, cfg)
        style, s_rows, s_raw = style_signal(store, cfg, base.style_mu, base.style_sd)
        behavior, b_rows, b_prof = behavior_signal(store, cfg, base.ngram_center, seed=cfg.seed)
        fview = store.funding.account_view(store.wallet[:n])
        funding = FundingSignal(fview, n)
        social = SocialSignal(store.follow_matrix())
        mark("signals")
        embed_job.result()
        mark("embed")
        content, c_rows, c_raw = content_signal(store, cfg, base.content_center)
        dense = {"timing": timing, "content": content, "style": style, "behavior": behavior}
        self.last_signals = dense
        mark("content")

        flagged = self._flag_mask(n)
        active = np.zeros(n, dtype=bool)
        for sig in dense.values():
            active[sig.rows] = True
        pool = np.flatnonzero(active & ~flagged)
        rp_i = rp_j = np.zeros(0, dtype=np.int64)
        if len(pool) >= 10:
            rp_i = rng.choice(pool, N_RANDOM_PAIRS)
            rp_j = rng.choice(pool, N_RANDOM_PAIRS)
            ok = rp_i != rp_j
            rp_i, rp_j = rp_i[ok], rp_j[ok]
        rsims = pair_similarities(dense, funding, social, rp_i, rp_j)
        if base.runs == 0:
            base.update_pairs(rsims, alpha=1.0)

        I, J = candidate_pairs(dense, funding, social, n, cfg.knn_k, rng, zfun=base.z, zmin=cfg.candidate_z)
        mark("knn")

        sims = pair_similarities(dense, funding, social, I, J)
        z = {name: base.z(name, s) for name, s in sims.items()}
        w, bits, _ = fuse(z, cfg)
        mark("fuse")

        groups = leiden_communities(n, I, J, w, cfg)
        groups = refine(groups, dense, I, J, w, n, cfg)
        groups = consolidate(groups, dense, I, J, w, n, cfg.min_community)
        groups = [g for g in groups if len(g) >= cfg.min_community]
        mark("communities")

        ctx = ScoringContext(dense, fview, store, net, store.now, {})
        label = np.full(n, -1, dtype=np.int64)
        for gi, g in enumerate(groups):
            label[g] = gi
        li, lj = label[I], label[J]
        internal = (li == lj) & (li >= 0)
        sum_w = np.bincount(li[internal], weights=w[internal], minlength=len(groups))
        cnt_w = np.bincount(li[internal], minlength=len(groups))
        ids = self.tracker.assign(groups, n, store.now)
        observed = store.now - (store.first_seen_t if store.first_seen_t is not None else store.now)
        mature = min(1.0, observed / (cfg.maturity_hours * 60.0)) if cfg.maturity_hours > 0 else 1.0
        clusters: list[Cluster] = []
        for gi, g in enumerate(groups):
            m = group_metrics(g, ctx)
            m["edge_weight"] = float(sum_w[gi] / cnt_w[gi]) if cnt_w[gi] else 0.0
            m["edge_density"] = float(2.0 * cnt_w[gi] / max(1, len(g) * (len(g) - 1)))
            s = strengths(m, base)
            prev = self.memory.get(ids[gi])
            if prev is not None:
                s = remember(s, prev[1], store.now - prev[0])
            self.memory[ids[gi]] = (store.now, {f: s.get(f, 0.0) for f in WEIGHTS})
            conf, _ = confidence(s, len(g))
            if mature < 1.0:  # no verdicts before the detector has learned what normal looks like
                conf = min(conf, 0.45)
            v = verdict(conf, s, m, cfg.swarm_threshold, cfg.min_community)
            if v == SWARM:
                session_script(g, ctx, m)
            ev = build_evidence(v, m, s, base, net)
            since = self.tracker.mark_flagged(ids[gi], store.now, v == SWARM)
            clusters.append(Cluster(ids[gi], v, conf, level_estimate(m) if v == SWARM else None, g, m, s, ev,
                                    self.tracker.first_seen.get(ids[gi], store.now), since))
        clusters.sort(key=lambda c: (c.verdict != SWARM, -c.confidence, -c.size))
        horizon = store.now - 48 * 60.0
        self.memory = {cid: v for cid, v in self.memory.items() if v[0] >= horizon}
        mark("scoring")

        new_flag = np.zeros(n, dtype=bool)
        for c in clusters:
            if c.verdict == SWARM:
                new_flag[c.members] = True
        self.flagged = new_flag
        if base.runs > 0:
            base.update_pairs(rsims, alpha)
        keep_c = ~new_flag[c_rows] if len(c_rows) else np.zeros(0, dtype=bool)
        keep_s = ~new_flag[s_rows] if len(s_rows) else np.zeros(0, dtype=bool)
        keep_b = ~new_flag[b_rows] if len(b_rows) else np.zeros(0, dtype=bool)
        base.update_vectors(c_raw[keep_c] if len(c_rows) else None, s_raw[keep_s] if len(s_rows) else None,
                            b_prof[keep_b] if len(b_rows) and len(b_prof) else None,
                            alpha=1.0 if base.runs == 0 else alpha)
        clean_pool = np.flatnonzero(active & ~new_flag)
        if len(clean_pool) >= RANDOM_GROUP_SIZE * 2:
            rows = []
            for _ in range(N_RANDOM_GROUPS):
                grp = rng.choice(clean_pool, RANDOM_GROUP_SIZE, replace=False)
                gm = group_metrics(grp, ctx, full=False)
                sample = set(grp.tolist())
                links = sum(len(store.follows[a] & sample) for a in grp.tolist())
                gm["follow_density"] = links / (RANDOM_GROUP_SIZE * (RANDOM_GROUP_SIZE - 1))
                rows.append({k: gm[k] for k in REF_KEYS if k in gm})
            base.update_groups(rows, alpha=1.0 if base.runs == 0 else alpha)
        base.set_communities([{k: c.metrics[k] for k in REF_KEYS if k in c.metrics}
                              for c in clusters if c.verdict == ORGANIC and c.confidence < 0.45])
        lat_pool = clean_pool[: 4000] if len(clean_pool) else clean_pool
        if len(lat_pool):
            sample = rng.choice(lat_pool, min(800, len(lat_pool)), replace=False)
            lats = np.array([ctx.latency_of(int(a)) for a in sample])
            lats = lats[np.isfinite(lats)]
            if len(lats) >= 30:
                base.update_latency(float(np.median(lats)), alpha=1.0 if base.latency_pop is None else alpha)
        base.runs += 1
        mark("baseline")

        weights = account_weights(n, clusters, cfg.weight_mode, cfg.flag_threshold)
        account_cluster = np.full(n, -1, dtype=np.int64)
        for c in clusters:
            account_cluster[c.members] = c.id
        vi, vj, vw, vb = self._viz_edges(I, J, w, bits, z, account_cluster, clusters)
        mark("output")

        result = DetectionResult(
            run=self.runs, t=store.now, latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
            stages=stages, n_accounts=n, n_active=int(active.sum()), clusters=clusters,
            edge_i=vi, edge_j=vj, edge_w=vw, edge_bits=vb, account_cluster=account_cluster, weights=weights,
            baseline=base.snapshot(), embedder=self.embedder.name, knn_backend=backend_name(),
            n_candidates=int(len(I)),
        )
        self.runs += 1
        self.last = result
        return result

    # -------------------------------------------------------------- helpers
    def _flag_mask(self, n: int) -> np.ndarray:
        mask = np.zeros(n, dtype=bool)
        m = min(n, len(self.flagged))
        mask[:m] = self.flagged[:m]
        return mask

    def _viz_edges(self, I, J, w, bits, z, account_cluster, clusters):
        """The edges worth drawing: each clustered account's strongest internal
        links, plus every other account's single strongest (faint) link."""
        cfg = self.cfg
        if len(I) == 0:
            empty = np.zeros(0, dtype=np.int64)
            return empty, empty, np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.uint8)
        shown = {c.id for c in clusters if c.verdict in (SWARM, ORGANIC)}
        ci, cj = account_cluster[I], account_cluster[J]
        in_shown = np.isin(ci, list(shown)) if shown else np.zeros(len(I), dtype=bool)
        internal = (ci == cj) & in_shown
        soft = np.zeros(len(I), dtype=np.float32)
        for name, zs in z.items():
            soft += ALPHA[name] * np.clip((np.nan_to_num(zs, nan=-1e9) - 1.0) / (cfg.z_full - 1.0), 0, 1)
        score = np.where(internal, 10.0 + w, 0.5 * soft + w).astype(np.float32)
        idx = np.flatnonzero(internal | (score > 0.4))
        Ii, Jj, sc, inner = I[idx], J[idx], score[idx], internal[idx]
        keep_int = inner & (_topk_mask(Ii, sc, 3) | _topk_mask(Jj, sc, 3))
        keep_bg = ~inner & (_topk_mask(Ii, sc, 1) | _topk_mask(Jj, sc, 1))
        keep = idx[keep_int | keep_bg]
        if len(keep) > cfg.viz_edges:
            keep = keep[np.argsort(-score[keep])[: cfg.viz_edges]]
        weight = np.where(internal[keep], w[keep], np.maximum(w[keep], 0.5 * soft[keep]))
        return I[keep], J[keep], weight.astype(np.float32), bits[keep]
