"""Funding ancestry over the public transfer ledger.

For every wallet we keep its first two funders ("who paid for this
address"). Ancestry walks those links upstream for up to k hops and stops
at hubs: exchange hot wallets (publicly labelled, like block explorers do)
or any unlabelled wallet that fans out to many recipients over a long
period. Sharing an exchange as a funder means nothing; sharing a private
wallet three hops up means a lot.

Ancestry is maintained incrementally: when a wallet gains a first funder
(or a wallet turns into a hub) only its descendants within k hops are
recomputed.
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix

from ..config import DetectorConfig


class FundingGraph:
    def __init__(self, cfg: DetectorConfig) -> None:
        self.cfg = cfg
        self.k = cfg.funding_hops
        self.cursor = 0
        self.first_funders: dict[int, list[tuple[float, int]]] = {}
        self.children: dict[int, set[int]] = {}
        self.out_count: dict[int, int] = {}
        self.out_first: dict[int, float] = {}
        self.out_last: dict[int, float] = {}
        self.labels: list[str | None] = []
        self._hub: dict[int, bool] = {}
        self._anc: dict[int, dict[int, int]] = {}
        self._dirty: set[int] = set()
        self.version = 0
        self._view: dict | None = None
        self._view_key: tuple[int, int] = (-1, -1)

    # ------------------------------------------------------------- ingest
    def _mark(self, w: int) -> None:
        stack = [(w, 0)]
        seen: set[int] = set()
        while stack:
            node, depth = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            self._dirty.add(node)
            if depth < self.k and not self._hub.get(node, False):
                for c in self.children.get(node, ()):
                    stack.append((c, depth + 1))

    def ingest(self, net) -> int:
        n_tx = net.tx_t.n
        self.labels = net.wallet_label
        if self.cursor >= n_tx:
            return 0
        ts = net.tx_t.a[self.cursor:n_tx].tolist()
        src = net.tx_src.a[self.cursor:n_tx].tolist()
        dst = net.tx_dst.a[self.cursor:n_tx].tolist()
        touched_src: set[int] = set()
        for t, s, d in zip(ts, src, dst):
            lst = self.first_funders.setdefault(d, [])
            if len(lst) < 2 or t < lst[-1][0]:
                old = {f for _, f in lst}
                lst.append((t, s))
                lst.sort()
                del lst[2:]
                new = {f for _, f in lst}
                if new != old:
                    for f in old - new:
                        self.children.get(f, set()).discard(d)
                    for f in new - old:
                        self.children.setdefault(f, set()).add(d)
                    self._mark(d)
            self.out_count[s] = self.out_count.get(s, 0) + 1
            if s not in self.out_first or t < self.out_first[s]:
                self.out_first[s] = t
            if s not in self.out_last or t > self.out_last[s]:
                self.out_last[s] = t
            touched_src.add(s)
        for s in touched_src:
            was = self._hub.get(s)
            now = self._compute_hub(s)
            if was is None or was != now:
                self._hub[s] = now
                if was is not None:
                    for c in self.children.get(s, ()):
                        self._mark(c)
        added = n_tx - self.cursor
        self.cursor = n_tx
        return added

    # ------------------------------------------------------------ queries
    def _compute_hub(self, w: int) -> bool:
        if w < len(self.labels) and self.labels[w]:
            return True
        if self.out_count.get(w, 0) < self.cfg.hub_min_recipients:
            return False
        span = self.out_last.get(w, 0.0) - self.out_first.get(w, 0.0)
        return span >= self.cfg.hub_min_span_days * 1440.0

    def is_hub(self, w: int) -> bool:
        hub = self._hub.get(w)
        if hub is None:
            hub = self._compute_hub(w)
            self._hub[w] = hub
        return hub

    def _compute(self, w: int) -> dict[int, int]:
        out: dict[int, int] = {}
        frontier = [w]
        seen = {w}
        for hop in range(1, self.k + 1):
            nxt = []
            for node in frontier:
                for _, f in self.first_funders.get(node, ()):
                    if f in seen or self.is_hub(f):
                        continue
                    seen.add(f)
                    out[f] = hop
                    nxt.append(f)
            if not nxt:
                break
            frontier = nxt
        return out

    def ancestors(self, w: int) -> dict[int, int]:
        if w in self._dirty or w not in self._anc:
            self._anc[w] = self._compute(w)
            self._dirty.discard(w)
        return self._anc[w]

    def account_view(self, wallets: np.ndarray) -> dict:
        """Per-account funding facts for the given account wallets.

        first_t   first incoming transfer time (NaN if never funded)
        first_hub hub wallet of the first funder, -1 if the funder is not a hub
        root      deepest non-hub ancestor within k hops (-1 if none), root_hops
        anc       CSR (n x n_cols) hop-decayed ancestry weights, L2-normalised
        anc_cols  wallet id of each ancestry column
        """
        wl = wallets.tolist()
        stale = any(w in self._dirty or w not in self._anc for w in wl)
        if stale:
            self.version += 1
        key = (self.version, len(wl))
        if self._view is not None and self._view_key == key:
            return self._view
        n = len(wl)
        first_t = np.full(n, np.nan)
        first_hub = np.full(n, -1, dtype=np.int64)
        root = np.full(n, -1, dtype=np.int64)
        root_hops = np.zeros(n, dtype=np.int64)
        rows, cols, vals = [], [], []
        col_of: dict[int, int] = {}
        for i, w in enumerate(wl):
            funders = self.first_funders.get(w)
            if not funders:
                continue
            t0, f0 = funders[0]
            first_t[i] = t0
            if self.is_hub(f0):
                first_hub[i] = f0
            anc = self.ancestors(w)
            if not anc:
                continue
            best_h, best_a = -1, -1
            for a, h in anc.items():
                c = col_of.setdefault(a, len(col_of))
                rows.append(i)
                cols.append(c)
                vals.append(0.75 ** (h - 1))
                if h > best_h or (h == best_h and a < best_a):
                    best_h, best_a = h, a
            root[i] = best_a
            root_hops[i] = best_h
        anc_m = csr_matrix((np.asarray(vals, dtype=np.float32), (rows, cols)), shape=(n, max(1, len(col_of))))
        norms = np.sqrt(np.asarray(anc_m.multiply(anc_m).sum(axis=1)).ravel())
        norms[norms == 0] = 1.0
        anc_m = csr_matrix(anc_m.multiply(1.0 / norms[:, None]), dtype=np.float32)
        anc_cols = np.zeros(len(col_of), dtype=np.int64)
        for a, c in col_of.items():
            anc_cols[c] = a
        self._view = {"first_t": first_t, "first_hub": first_hub, "root": root, "root_hops": root_hops,
                      "anc": anc_m, "anc_cols": anc_cols}
        self._view_key = key
        return self._view
