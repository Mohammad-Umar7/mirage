"""What "normal" looks like in this network, learned without labels.

Two kinds of reference are tracked with slow exponential moving averages,
updated only from accounts that are not currently flagged:

* pair statistics per signal (median and robust scale of similarity
  between random accounts) - used to z-score candidate edges;
* group statistics (typical metric values of random account groups and of
  the organic communities the detector found) - used to score clusters and
  to phrase evidence ("real communities in this network: 0.18").

Because the reference moves slowly and excludes flagged accounts, a swarm
that appears suddenly cannot redefine "normal" before it is caught.
"""

from __future__ import annotations

import numpy as np

FLOORS = {"timing": 0.05, "content": 0.05, "style": 0.06, "behavior": 0.05, "funding": 0.1}


class Baseline:
    def __init__(self, alpha: float = 0.08) -> None:
        self.alpha = alpha
        self.pair: dict[str, tuple[float, float]] = {}
        self.group: dict[str, float] = {}
        self.community: dict[str, float] = {}
        self.content_center: np.ndarray | None = None
        self.style_mu: np.ndarray | None = None
        self.style_sd: np.ndarray | None = None
        self.ngram_center: np.ndarray | None = None
        self.latency_pop: float | None = None
        self.runs = 0

    def _ema(self, old, new, alpha: float):
        if old is None:
            return new
        return (1.0 - alpha) * old + alpha * new

    # --------------------------------------------------------------- pairs
    def update_pairs(self, sims: dict[str, np.ndarray], alpha: float | None = None) -> None:
        alpha = self.alpha if alpha is None else alpha
        for name, s in sims.items():
            s = s[np.isfinite(s)]
            if len(s) < 50:
                continue
            med = float(np.median(s))
            scale = float(1.4826 * np.median(np.abs(s - med)))
            scale = max(scale, FLOORS.get(name, 0.05))
            old = self.pair.get(name)
            if old is None:
                self.pair[name] = (med, scale)
            else:
                self.pair[name] = (self._ema(old[0], med, alpha), self._ema(old[1], scale, alpha))

    def z(self, name: str, sims: np.ndarray) -> np.ndarray:
        med, scale = self.pair.get(name, (0.0, FLOORS.get(name, 0.05)))
        return (sims - med) / scale

    # ------------------------------------------------------------- vectors
    def update_vectors(self, content_raw: np.ndarray | None, style_raw: np.ndarray | None,
                       ngrams: np.ndarray | None, alpha: float | None = None) -> None:
        alpha = self.alpha if alpha is None else alpha
        if content_raw is not None and len(content_raw) >= 20:
            self.content_center = self._ema(self.content_center, content_raw.mean(axis=0), alpha)
        if style_raw is not None and len(style_raw) >= 20:
            self.style_mu = self._ema(self.style_mu, np.median(style_raw, axis=0), alpha)
            self.style_sd = self._ema(self.style_sd, style_raw.std(axis=0), alpha)
        if ngrams is not None and len(ngrams) >= 20:
            self.ngram_center = self._ema(self.ngram_center, np.median(ngrams, axis=0), alpha)

    # -------------------------------------------------------------- groups
    def update_groups(self, rows: list[dict[str, float]], alpha: float | None = None) -> None:
        alpha = self.alpha if alpha is None else alpha
        for key in {k for r in rows for k in r}:
            vals = [r[key] for r in rows if key in r and r[key] == r[key]]
            if vals:
                self.group[key] = self._ema(self.group.get(key), float(np.median(vals)), alpha)

    def set_communities(self, rows: list[dict[str, float]]) -> None:
        out: dict[str, float] = {}
        if len(rows) >= 2:
            for key in {k for r in rows for k in r}:
                vals = [r[key] for r in rows if key in r and r[key] == r[key]]
                if len(vals) >= 2:
                    out[key] = float(np.median(vals))
        self.community = out

    def update_latency(self, value: float, alpha: float | None = None) -> None:
        if value == value:
            self.latency_pop = self._ema(self.latency_pop, value, self.alpha if alpha is None else alpha)

    def reference(self, key: str) -> tuple[float, str]:
        """Reference value and a human label for where it came from."""
        if key in self.community:
            return self.community[key], "real communities in this network"
        if key in self.group:
            return self.group[key], "typical account groups"
        return float("nan"), "n/a"

    def snapshot(self) -> dict:
        return {
            "pair": {k: [round(v[0], 4), round(v[1], 4)] for k, v in self.pair.items()},
            "group": {k: round(v, 4) for k, v in self.group.items()},
            "community": {k: round(v, 4) for k, v in self.community.items()},
            "latency_pop": self.latency_pop,
            "runs": self.runs,
        }
