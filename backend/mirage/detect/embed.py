"""Text embedders for the content signal.

* ``MiniLMEmbedder`` - local sentence-transformers ``all-MiniLM-L6-v2``
  (384-d). Uses CUDA when available. Loads from the local HuggingFace cache
  first so it works offline after the first download.
* ``HashingEmbedder`` - dependency-light fallback: hashed word and char
  n-grams through a fixed random projection (256-d). Always available.
"""

from __future__ import annotations

import os
from collections import OrderedDict

import numpy as np

from ..util import l2_normalize

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class HashingEmbedder:
    name = "hashing"

    def __init__(self, dim: int = 256, n_features: int = 2**13, seed: int = 0) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer

        self.dim = dim
        self._words = HashingVectorizer(n_features=n_features, ngram_range=(1, 2), alternate_sign=False,
                                        norm="l2", lowercase=True)
        self._chars = HashingVectorizer(n_features=n_features, analyzer="char_wb", ngram_range=(3, 5),
                                        alternate_sign=False, norm="l2", lowercase=True)
        rng = np.random.default_rng(seed)
        self._proj = (rng.standard_normal((2 * n_features, dim)) / np.sqrt(dim)).astype(np.float32)

    def encode(self, texts: list[str]) -> np.ndarray:
        from scipy.sparse import hstack

        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        X = hstack([self._words.transform(texts), self._chars.transform(texts) * 0.7]).tocsr()
        return l2_normalize(np.asarray(X @ self._proj, dtype=np.float32))


class MiniLMEmbedder:
    name = "minilm"

    def __init__(self, device: str | None = None) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        try:
            self.model = SentenceTransformer(MODEL_NAME, device=self.device, local_files_only=True)
        except Exception:
            self.model = SentenceTransformer(MODEL_NAME, device=self.device)
        self.dim = int(self.model.get_sentence_embedding_dimension())

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = self.model.encode(texts, batch_size=256, normalize_embeddings=True, convert_to_numpy=True,
                                show_progress_bar=False)
        return np.asarray(out, dtype=np.float32)


class CachedEmbedder:
    """Memoises embeddings by exact text (naive swarms repeat themselves)."""

    def __init__(self, inner, capacity: int = 50_000) -> None:
        self.inner = inner
        self.name = inner.name
        self.dim = inner.dim
        self.capacity = capacity
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        missing: dict[str, list[int]] = {}
        for i, text in enumerate(texts):
            vec = self._cache.get(text)
            if vec is None:
                missing.setdefault(text, []).append(i)
            else:
                self._cache.move_to_end(text)
                out[i] = vec
        if missing:
            uniq = list(missing)
            vecs = self.inner.encode(uniq)
            for text, vec in zip(uniq, vecs):
                for i in missing[text]:
                    out[i] = vec
                self._cache[text] = vec
            while len(self._cache) > self.capacity:
                self._cache.popitem(last=False)
        return out


def make_embedder(kind: str = "auto"):
    kind = os.environ.get("MIRAGE_EMBEDDER", kind).lower()
    if kind in ("auto", "minilm"):
        try:
            return CachedEmbedder(MiniLMEmbedder())
        except Exception:
            if kind == "minilm":
                raise
    return CachedEmbedder(HashingEmbedder())
