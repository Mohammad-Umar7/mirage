"""Incremental per-account features built from the public event log.

The store consumes ``NetworkState`` append-only columns from a cursor, so
each detection run only pays for the events that arrived since the last
run. Everything is keyed by account index and computed from public data.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from ..config import DetectorConfig
from ..network import EventKind
from .funding import FundingGraph
from .stylometry import N_FEATURES, style_vector

CO_REPLY, CO_FOLLOW, CO_VOTE, CO_TRANSFER = 1, 2, 3, 4
ACTION_CODE = {int(EventKind.POST): 1, int(EventKind.REPLY): 2, int(EventKind.FOLLOW): 3,
               int(EventKind.TRANSFER): 4, int(EventKind.VOTE): 5, int(EventKind.PROPOSE): 6}
ACTION_NAME = {1: "post", 2: "reply", 3: "follow", 4: "transfer", 5: "vote", 6: "propose"}


class FeatureStore:
    def __init__(self, cfg: DetectorConfig, embedder) -> None:
        self.cfg = cfg
        self.embedder = embedder
        self.B = int(round(cfg.window_hours * 60.0 / cfg.bin_minutes))
        self.bin_min = float(cfg.bin_minutes)
        self.window = float(cfg.window_hours * 60.0)
        self.P = cfg.posts_per_account
        self.Ps = cfg.style_posts_per_account
        self.dim = embedder.dim
        self.n = 0
        self.cap = 0
        self.head: int | None = None
        self.now = 0.0
        self.cursor = 0
        self.act = np.zeros((0, self.B), dtype=np.float32)
        self.emb = np.zeros((0, self.P, self.dim), dtype=np.float16)
        self.emb_t = np.zeros((0, self.P))
        self.emb_pos = np.zeros(0, dtype=np.int64)
        self.sty = np.zeros((0, self.Ps, N_FEATURES), dtype=np.float32)
        self.sty_t = np.zeros((0, self.Ps))
        self.sty_pos = np.zeros(0, dtype=np.int64)
        self.first_action = np.zeros(0)
        self.action_ver = np.zeros(0, dtype=np.int64)
        self.beh_cache: dict[int, tuple] = {}
        self.created = np.zeros(0)
        self.wallet = np.zeros(0, dtype=np.int64)
        self.actions: list[deque] = []
        self.coacts: list[deque] = []
        self.latency: list[deque] = []
        self.votes: list[dict[int, tuple[float, int]]] = []
        self.follows: list[set[int]] = []
        self.embed_queue: deque[tuple[int, int, float]] = deque()
        self.funding = FundingGraph(cfg)
        self.events_seen = 0

    # --------------------------------------------------------------- sizing
    def _grow(self, n: int) -> None:
        if n <= self.cap:
            return
        cap = max(n, int(self.cap * 1.5) + 256)
        extra = cap - self.cap

        def pad(a: np.ndarray, fill=0.0) -> np.ndarray:
            shape = (extra,) + a.shape[1:]
            return np.concatenate([a, np.full(shape, fill, dtype=a.dtype)], axis=0)

        self.act = pad(self.act)
        self.emb = pad(self.emb)
        self.emb_t = pad(self.emb_t, np.nan)
        self.emb_pos = pad(self.emb_pos)
        self.sty = pad(self.sty)
        self.sty_t = pad(self.sty_t, np.nan)
        self.sty_pos = pad(self.sty_pos)
        self.first_action = pad(self.first_action, np.nan)
        self.action_ver = pad(self.action_ver)
        self.created = pad(self.created, np.nan)
        self.wallet = pad(self.wallet, -1)
        self.cap = cap

    def _advance(self, now: float) -> None:
        head = int(math.floor((now - 1e-9) / self.bin_min))
        if self.head is None:
            self.head = head
            return
        steps = head - self.head
        if steps <= 0:
            return
        if steps >= self.B:
            self.act[:] = 0.0
        else:
            cols = [(self.head + s) % self.B for s in range(1, steps + 1)]
            self.act[:, cols] = 0.0
        self.head = head

    # --------------------------------------------------------------- ingest
    def sync(self, net) -> int:
        """Consume new public events. Returns number of events ingested."""
        n_acc = net.n_accounts
        if n_acc > self.n:
            self._grow(n_acc)
            self.created[self.n:n_acc] = net.acct_created.a[self.n:n_acc]
            self.wallet[self.n:n_acc] = net.acct_wallet.a[self.n:n_acc]
            for _ in range(self.n, n_acc):
                self.actions.append(deque(maxlen=96))
                self.coacts.append(deque(maxlen=64))
                self.latency.append(deque(maxlen=32))
                self.votes.append({})
                self.follows.append(set())
            self.n = n_acc
        self.now = float(net.now)
        self._advance(self.now)
        self.funding.ingest(net)

        start, end = self.cursor, net.n_events
        if end <= start:
            return 0
        ts = net.ev_t.a[start:end]
        kinds = net.ev_kind.a[start:end]
        actors = net.ev_actor.a[start:end]
        objs = net.ev_obj.a[start:end]
        auxs = net.ev_aux.a[start:end]

        is_action = (kinds != EventKind.JOIN) & (actors >= 0)
        b = np.floor(ts / self.bin_min).astype(np.int64)
        in_win = is_action & (b > self.head - self.B) & (b <= self.head)
        np.add.at(self.act, (actors[in_win], b[in_win] % self.B), 1.0)

        post_text = net.post_text
        post_t = net.post_t.a
        for t, k, a, o, x in zip(ts.tolist(), kinds.tolist(), actors.tolist(), objs.tolist(), auxs.tolist()):
            if k == EventKind.JOIN or a < 0:
                continue
            self.actions[a].append((t, ACTION_CODE.get(k, 0)))
            self.action_ver[a] += 1
            fa = self.first_action[a]
            if fa != fa or t < fa:
                self.first_action[a] = t
            if k == EventKind.POST or k == EventKind.REPLY:
                pos = self.sty_pos[a] % self.Ps
                self.sty[a, pos] = style_vector(post_text[o])
                self.sty_t[a, pos] = t
                self.sty_pos[a] += 1
                self.embed_queue.append((o, a, t))
                if k == EventKind.REPLY and x >= 0:
                    self.latency[a].append((t, t - float(post_t[x])))
                    self.coacts[a].append((t, CO_REPLY, x))
            elif k == EventKind.FOLLOW:
                self.follows[a].add(o)
                self.coacts[a].append((t, CO_FOLLOW, o))
            elif k == EventKind.VOTE:
                self.votes[a].setdefault(o, (t, x))
                self.coacts[a].append((t, CO_VOTE, o * 2 + x))
            elif k == EventKind.TRANSFER:
                self.coacts[a].append((t, CO_TRANSFER, x))
        self.cursor = end
        self.events_seen += end - start
        return end - start

    def embed_pending(self, net, budget: int) -> int:
        """Embed up to ``budget`` queued posts (oldest first)."""
        if not self.embed_queue:
            return 0
        take = min(budget, len(self.embed_queue))
        batch = [self.embed_queue.popleft() for _ in range(take)]
        cutoff = self.now - self.window
        batch = [x for x in batch if x[2] >= cutoff]
        if not batch:
            return 0
        vecs = self.embedder.encode([net.post_text[pid] for pid, _, _ in batch]).astype(np.float16)
        for (pid, a, t), v in zip(batch, vecs):
            pos = self.emb_pos[a] % self.P
            self.emb[a, pos] = v
            self.emb_t[a, pos] = t
            self.emb_pos[a] += 1
        return len(batch)

    # -------------------------------------------------------------- views
    def timing_matrix(self) -> np.ndarray:
        """(n, B) activity counts in chronological bin order."""
        cols = (np.arange(self.head - self.B + 1, self.head + 1) % self.B)
        return self.act[: self.n][:, cols]

    def content_means(self) -> tuple[np.ndarray, np.ndarray]:
        """Mean post embedding per account over the window, and post counts."""
        n = self.n
        valid = self.emb_t[:n] >= self.now - self.window
        counts = valid.sum(axis=1)
        sums = np.einsum("np,npd->nd", valid.astype(np.float32), self.emb[:n].astype(np.float32))
        means = sums / np.maximum(counts, 1)[:, None]
        return means.astype(np.float32), counts

    def style_means(self) -> tuple[np.ndarray, np.ndarray]:
        n = self.n
        valid = self.sty_t[:n] >= self.now - self.window
        counts = valid.sum(axis=1)
        sums = np.einsum("np,npd->nd", valid.astype(np.float32), self.sty[:n])
        return (sums / np.maximum(counts, 1)[:, None]).astype(np.float32), counts

    def window_actions(self, a: int) -> list[tuple[float, int]]:
        cutoff = self.now - self.window
        return sorted(x for x in self.actions[a] if x[0] >= cutoff)

    def median_latency(self) -> np.ndarray:
        cutoff = self.now - self.window
        out = np.full(self.n, np.nan)
        for a in range(self.n):
            lat = [v for t, v in self.latency[a] if t >= cutoff and v >= 0]
            if lat:
                out[a] = float(np.median(lat))
        return out
