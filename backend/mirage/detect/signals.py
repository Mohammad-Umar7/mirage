"""Per-signal account vectors: timing, content, style, behaviour, funding.

Each dense signal is a set of L2-normalised vectors for the accounts that
have enough data for it, so cosine similarity between two accounts is a
dot product (for timing: Pearson correlation of smoothed activity).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.utils.extmath import randomized_svd

from ..config import DetectorConfig
from .features import CO_FOLLOW, CO_REPLY, CO_TRANSFER, CO_VOTE, FeatureStore

DENSE_SIGNALS = ("timing", "content", "style", "behavior")
SIGNALS = DENSE_SIGNALS + ("funding",)
N_NGRAM = 620
SESSION_GAP = 45.0


@dataclass
class DenseSignal:
    name: str
    rows: np.ndarray
    X: np.ndarray
    pos: np.ndarray

    @classmethod
    def build(cls, name: str, n: int, rows: np.ndarray, V: np.ndarray) -> "DenseSignal":
        V = np.asarray(V, dtype=np.float32)
        norms = np.linalg.norm(V, axis=1)
        ok = norms > 1e-8
        rows, V, norms = rows[ok], V[ok], norms[ok]
        X = (V / norms[:, None]).astype(np.float32)
        pos = np.full(n, -1, dtype=np.int64)
        pos[rows] = np.arange(len(rows))
        return cls(name, rows.astype(np.int64), X, pos)

    def pair_sim(self, I: np.ndarray, J: np.ndarray, chunk: int = 50_000) -> np.ndarray:
        out = np.full(len(I), np.nan, dtype=np.float32)
        pi, pj = self.pos[I], self.pos[J]
        ok = np.flatnonzero((pi >= 0) & (pj >= 0))
        for s in range(0, len(ok), chunk):
            sel = ok[s:s + chunk]
            out[sel] = np.einsum("ij,ij->i", self.X[pi[sel]], self.X[pj[sel]])
        return out

    def vectors(self, members: np.ndarray) -> np.ndarray:
        p = self.pos[members]
        return self.X[p[p >= 0]]


# ------------------------------------------------------------------ builders
def timing_signal(store: FeatureStore, cfg: DetectorConfig) -> DenseSignal:
    """Band-passed activity series.

    A light smoothing tolerates minutes of jitter; subtracting a ~2 hour
    smooth removes daily rhythm, so two people who simply live in the same
    timezone do not correlate - only sharp, co-timed bursts do.
    """
    A = store.timing_matrix()
    rows = np.flatnonzero(A.sum(axis=1) >= cfg.min_events)
    M = np.log1p(A[rows])
    fine = gaussian_filter1d(M, sigma=cfg.smooth_bins, axis=1, mode="constant")
    coarse = gaussian_filter1d(M, sigma=cfg.smooth_bins * 5.0, axis=1, mode="constant")
    M = fine - coarse
    M -= M.mean(axis=1, keepdims=True)
    return DenseSignal.build("timing", store.n, rows, M.astype(np.float32))


def content_signal(store: FeatureStore, cfg: DetectorConfig, center: np.ndarray | None
                   ) -> tuple[DenseSignal, np.ndarray, np.ndarray]:
    means, counts = store.content_means()
    rows = np.flatnonzero(counts >= cfg.min_posts)
    raw = means[rows]
    raw_n = raw / np.maximum(np.linalg.norm(raw, axis=1, keepdims=True), 1e-8)
    V = raw_n - center if center is not None else raw_n
    return DenseSignal.build("content", store.n, rows, V), rows, raw_n


def style_signal(store: FeatureStore, cfg: DetectorConfig, mu: np.ndarray | None, sd: np.ndarray | None
                 ) -> tuple[DenseSignal, np.ndarray, np.ndarray]:
    means, counts = store.style_means()
    rows = np.flatnonzero(counts >= cfg.min_posts)
    raw = means[rows]
    if mu is None:
        mu = np.median(raw, axis=0) if len(raw) else np.zeros(raw.shape[1], dtype=np.float32)
        sd = raw.std(axis=0) if len(raw) else np.ones(raw.shape[1], dtype=np.float32)
    Z = (raw - mu) / np.maximum(sd, 1e-3)
    return DenseSignal.build("style", store.n, rows, np.clip(Z, -6, 6)), rows, raw


def _sessions(actions: list[tuple[float, int]]) -> list[list[int]]:
    sessions: list[list[int]] = []
    last = None
    for t, code in actions:
        if last is None or t - last > SESSION_GAP:
            sessions.append([])
        sessions[-1].append(code)
        last = t
    return sessions


def ngram_profile(actions: list[tuple[float, int]]) -> np.ndarray:
    v = np.zeros(N_NGRAM, dtype=np.float32)
    for s in _sessions(actions):
        v[600 + s[0]] += 1.0
        v[610 + min(len(s), 5)] += 1.0
        for a, b in zip(s, s[1:]):
            v[8 + a * 8 + b] += 1.0
        for a, b, c in zip(s, s[1:], s[2:]):
            v[100 + a * 64 + b * 8 + c] += 1.0
    total = v.sum()
    return v / total if total > 0 else v


def _account_behavior(store: FeatureStore, a: int, cutoff: float, min_events: int) -> tuple:
    """(count, n-gram profile, co-action token keys, earliest time used) for one account.

    Cached until the account acts again or its oldest counted action leaves
    the window, so a run only recomputes the accounts that changed.
    """
    ver = int(store.action_ver[a])
    cached = store.beh_cache.get(a)
    if cached is not None and cached[0] == ver and cached[1] >= cutoff:
        return cached[2], cached[3], cached[4]
    acts = store.window_actions(a)
    earliest = acts[0][0] if acts else float("inf")
    profile = ngram_profile(acts) if len(acts) >= min_events else None
    keys: list[int] = []
    for t, code, obj in store.coacts[a]:
        if t < cutoff:
            continue
        earliest = min(earliest, t)
        width = 120.0 if code == CO_VOTE else 60.0
        for shift in (0.0, width / 2):
            bucket = int((t + shift) // width)
            keys.append(((code * 4 + (1 if shift else 0)) << 50) | (int(obj) << 18) | (bucket & 0x3FFFF))
    store.beh_cache[a] = (ver, earliest, len(acts), profile, keys)
    return len(acts), profile, keys


def behavior_signal(store: FeatureStore, cfg: DetectorConfig, ngram_center: np.ndarray | None,
                    seed: int = 0) -> tuple[DenseSignal, np.ndarray, np.ndarray]:
    n = store.n
    cutoff = store.now - store.window
    rows: list[int] = []
    profiles: list[np.ndarray] = []
    tok_rows: list[int] = []
    tok_keys: list[int] = []
    for a in np.flatnonzero(store.action_ver[:n] >= cfg.min_events).tolist():
        count, profile, keys = _account_behavior(store, a, cutoff, cfg.min_events)
        if count < cfg.min_events or profile is None:
            continue
        r = len(rows)
        rows.append(a)
        profiles.append(profile)
        tok_rows.extend([r] * len(keys))
        tok_keys.extend(keys)
    rows_a = np.asarray(rows, dtype=np.int64)
    if len(rows_a) < 3:
        return DenseSignal.build("behavior", n, rows_a, np.zeros((len(rows_a), 8))), rows_a, np.zeros((0, N_NGRAM))
    P = np.vstack(profiles)
    center = ngram_center if ngram_center is not None else np.median(P, axis=0)
    Pc = P - center
    k1 = min(24, min(Pc.shape) - 1)
    U, S, _ = randomized_svd(Pc, n_components=k1, random_state=seed, n_iter=3)
    ng = U * S
    ng /= np.maximum(np.linalg.norm(ng, axis=1, keepdims=True), 1e-8)
    parts = [0.6 * ng]
    if tok_keys:
        keys = np.asarray(tok_keys, dtype=np.int64)
        uniq, col = np.unique(keys, return_inverse=True)
        M = csr_matrix((np.ones(len(col), dtype=np.float32), (np.asarray(tok_rows), col)),
                       shape=(len(rows_a), len(uniq)))
        M.data[:] = 1.0
        df = np.asarray((M > 0).sum(axis=0)).ravel()
        keep = np.flatnonzero((df >= 2) & (df <= 0.5 * len(rows_a)))
        if len(keep) >= 4:
            M = M[:, keep]
            idf = np.log(len(rows_a) / df[keep]).astype(np.float32)
            M = csr_matrix(M.multiply(idf[None, :]))
            k2 = min(32, min(M.shape) - 1)
            co = TruncatedSVD(n_components=k2, algorithm="randomized", n_iter=4, random_state=seed).fit_transform(M)
            norms = np.linalg.norm(co, axis=1, keepdims=True)
            co = np.where(norms > 1e-8, co / np.maximum(norms, 1e-8), 0.0)
            parts.append(0.8 * co)
    V = np.hstack(parts)
    return DenseSignal.build("behavior", n, rows_a, V), rows_a, P


# ------------------------------------------------------------------ funding
@dataclass
class FundingSignal:
    view: dict
    n: int

    def pair_sim(self, I: np.ndarray, J: np.ndarray) -> np.ndarray:
        anc = self.view["anc"]
        out = np.asarray(anc[I].multiply(anc[J]).sum(axis=1)).ravel().astype(np.float32)
        hub_i, hub_j = self.view["first_hub"][I], self.view["first_hub"][J]
        ti, tj = self.view["first_t"][I], self.view["first_t"][J]
        same_hub = (hub_i >= 0) & (hub_i == hub_j)
        dt = np.abs(ti - tj)
        hubco = np.where(same_hub & np.isfinite(dt), 0.5 * np.exp(-np.nan_to_num(dt, nan=1e9) / 30.0), 0.0)
        return np.maximum(out, hubco.astype(np.float32))

    def candidates(self, k: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        """Link accounts that share a non-hub ancestor or a hub + 30-minute funding bucket."""
        groups: dict[tuple[int, int], list[int]] = {}
        anc = self.view["anc"]
        cols = self.view["anc_cols"]
        indptr, indices = anc.indptr, anc.indices
        for i in range(self.n):
            for c in indices[indptr[i]:indptr[i + 1]]:
                groups.setdefault((0, int(cols[c])), []).append(i)
        hub = self.view["first_hub"]
        ft = self.view["first_t"]
        for i in np.flatnonzero(hub >= 0):
            groups.setdefault((1, int(hub[i]) * 100000 + int(ft[i] // 30.0) % 100000), []).append(int(i))
        I: list[np.ndarray] = []
        J: list[np.ndarray] = []
        for members in groups.values():
            m = len(members)
            if m < 2:
                continue
            arr = np.asarray(members, dtype=np.int64)
            if m <= k + 1:
                a, b = np.triu_indices(m, 1)
                I.append(arr[a])
                J.append(arr[b])
            else:
                perm = arr[rng.permutation(m)]
                for step in range(1, k // 2 + 1):
                    I.append(perm)
                    J.append(np.roll(perm, step))
        if not I:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        return np.concatenate(I), np.concatenate(J)
