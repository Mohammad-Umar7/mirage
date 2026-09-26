"""k-nearest-neighbour search over L2-normalised vectors (cosine similarity).

Uses FAISS when installed, otherwise scikit-learn's brute-force search.
Both compute neighbours in blocks; the n x n similarity matrix is never
materialised, so this scales to 10k+ accounts.
"""

from __future__ import annotations

import os

import numpy as np

try:  # optional dependency
    import faiss  # type: ignore

    faiss.omp_set_num_threads(max(1, min(8, (os.cpu_count() or 2) // 2)))
    HAVE_FAISS = True
except Exception:  # pragma: no cover - depends on environment
    faiss = None
    HAVE_FAISS = False


def knn(X: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (neighbours, similarities), each (n, k'), excluding self."""
    n = len(X)
    if n < 2:
        return np.zeros((n, 0), dtype=np.int64), np.zeros((n, 0), dtype=np.float32)
    k_eff = min(k + 1, n)
    X = np.ascontiguousarray(X, dtype=np.float32)
    if HAVE_FAISS:
        index = faiss.IndexFlatIP(X.shape[1])
        index.add(X)
        sims, idx = index.search(X, k_eff)
    else:
        from sklearn.neighbors import NearestNeighbors

        nn = NearestNeighbors(n_neighbors=k_eff, metric="cosine", algorithm="brute")
        dist, idx = nn.fit(X).kneighbors(X)
        sims = 1.0 - dist
    # Drop each row's self match. With duplicate vectors self is not always
    # ranked first, so move it to the end with a stable sort and truncate.
    is_self = idx == np.arange(n)[:, None]
    order = np.argsort(is_self, axis=1, kind="stable")
    idx = np.take_along_axis(idx, order, axis=1)[:, : k_eff - 1].astype(np.int64)
    sims = np.take_along_axis(sims, order, axis=1)[:, : k_eff - 1].astype(np.float32)
    return idx, sims


def backend_name() -> str:
    return "faiss" if HAVE_FAISS else "sklearn"
