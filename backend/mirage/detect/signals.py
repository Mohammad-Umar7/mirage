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

from ..config import DetectorConfig
from .features import CO_VOTE, FeatureStore

DENSE_SIGNALS = ("timing", "content", "style", "behavior")
SIGNALS = DENSE_SIGNALS + ("funding", "social")
N_NGRAM = 620
SESSION_GAP = 45.0


def top_directions(X: np.ndarray, k: int) -> np.ndarray:
    """(d, k) top principal directions of X's second moment, via a d x d
    eigendecomposition of only the top-k pairs - exact, and far cheaper
    than an SVD of X when n >> d."""
    from scipy.linalg import eigh

    C = (X.T @ X).astype(np.float64)
    d = C.shape[0]
    k = min(k, d)
    _, vecs = eigh(C, subset_by_index=[d - k, d - 1], driver="evr")
    return vecs[:, ::-1].astype(np.float32)


@dataclass
class DenseSignal:
    name: str
    rows: np.ndarray
    X: np.ndarray
    pos: np.ndarray

    @classmethod
    def build(cls, name: str, n: int, rows: np.ndarray, V: np.ndarray, project: int | None = None,
              seed: int = 0) -> "DenseSignal":
        """Normalise rows; optionally project onto the top `project` principal
        directions WITHOUT renormalising, so dot products approximate the
        original cosines (and shrink for accounts the subspace explains poorly)."""
        V = np.asarray(V, dtype=np.float32)
        norms = np.linalg.norm(V, axis=1)
        ok = norms > 1e-8
        rows, V, norms = rows[ok], V[ok], norms[ok]
        X = (V / norms[:, None]).astype(np.float32)
        if project is not None and X.shape[1] > project and len(X) > project * 2:
            X = (X @ top_directions(X, project)).astype(np.float32)
        pos = np.full(n, -1, dtype=np.int64)
        pos[rows] = np.arange(len(rows))
        return cls(name, rows.astype(np.int64), np.ascontiguousarray(X), pos)

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
    rows = np.flatnonzero(A.sum(axis=1) >= cfg.min_timing_events)
    M = np.log1p(A[rows])
    fine = gaussian_filter1d(M, sigma=cfg.smooth_bins, axis=1, mode="constant")
    coarse = gaussian_filter1d(M, sigma=cfg.smooth_bins * 5.0, axis=1, mode="constant")
    M = fine - coarse
    M -= M.mean(axis=1, keepdims=True)
    return DenseSignal.build("timing", store.n, rows, M.astype(np.float32), project=cfg.timing_dims)


def content_signal(store: FeatureStore, cfg: DetectorConfig, center: np.ndarray | None
                   ) -> tuple[DenseSignal, np.ndarray, np.ndarray]:
    means, counts = store.content_means()
    rows = np.flatnonzero(counts >= cfg.min_posts)
    raw = means[rows]
    raw_n = raw / np.maximum(np.linalg.norm(raw, axis=1, keepdims=True), 1e-8)
    V = raw_n - center if center is not None else raw_n
    return DenseSignal.build("content", store.n, rows, V, project=cfg.content_dims), rows, raw_n


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
    used = np.flatnonzero(np.abs(Pc).sum(axis=0) > 0)
    Pc_used = Pc[:, used].astype(np.float32)
    k1 = min(24, max(1, len(used) - 1))
    ng = Pc_used @ top_directions(Pc_used, k1)
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

    def _groups(self) -> list[np.ndarray]:
        cached = self.view.get("_groups")
        if cached is not None:
            return cached
        anc = self.view["anc"].tocoo()
        cols = self.view["anc_cols"]
        keys = [cols[anc.col].astype(np.int64) * 2]
        members = [anc.row.astype(np.int64)]
        hub = self.view["first_hub"]
        ft = self.view["first_t"]
        hub_rows = np.flatnonzero(hub >= 0)
        if len(hub_rows):
            bucket = (ft[hub_rows] // 30.0).astype(np.int64)
            keys.append(((hub[hub_rows] * 1_000_003 + bucket) * 2 + 1).astype(np.int64))
            members.append(hub_rows.astype(np.int64))
        key = np.concatenate(keys)
        mem = np.concatenate(members)
        order = np.argsort(key, kind="stable")
        key, mem = key[order], mem[order]
        cuts = np.flatnonzero(np.diff(key)) + 1
        groups = [g for g in np.split(mem, cuts) if len(g) >= 2]
        self.view["_groups"] = groups
        return groups

    def candidates(self, k: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        """Link accounts that share a non-hub ancestor or a hub + 30-minute funding bucket.

        Members of each group are shuffled and every member is linked to the
        next k members of its group: all pairs for small groups, a random
        k-regular band for big ones - never all pairs of a 10k-member group.
        """
        groups = self._groups()
        if not groups:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        key = np.concatenate([np.full(len(g), gi, dtype=np.int64) for gi, g in enumerate(groups)])
        mem = np.concatenate(groups)
        order = np.lexsort((rng.random(len(mem)), key))
        key, mem = key[order], mem[order]
        I: list[np.ndarray] = []
        J: list[np.ndarray] = []
        for d in range(1, k + 1):
            same = key[:-d] == key[d:]
            if not same.any():
                break
            I.append(mem[:-d][same])
            J.append(mem[d:][same])
        if not I:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        return np.concatenate(I), np.concatenate(J)


@dataclass
class SocialSignal:
    """Direct social ties from public follow events.

    1.0 for a mutual follow, 0.6 for a one-way follow, 0 otherwise. Real
    communities are made of real ties; on its own a tie never creates an
    edge (single-signal edges are down-weighted in fusion).
    """

    F: csr_matrix

    def pair_sim(self, I: np.ndarray, J: np.ndarray) -> np.ndarray:
        if len(I) == 0:
            return np.zeros(0, dtype=np.float32)
        a = np.asarray(self.F[I, J]).ravel() > 0
        b = np.asarray(self.F[J, I]).ravel() > 0
        return np.where(a & b, 1.0, np.where(a | b, 0.6, 0.0)).astype(np.float32)

    def candidates(self) -> tuple[np.ndarray, np.ndarray]:
        """Mutual follows only: one-way ties are too common to seed edges."""
        mutual = self.F.multiply(self.F.T).tocoo()
        keep = mutual.row < mutual.col
        return mutual.row[keep].astype(np.int64), mutual.col[keep].astype(np.int64)
