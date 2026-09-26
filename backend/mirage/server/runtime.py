"""The live runtime: one thread that ticks the simulator and runs detection.

Each tick: advance the simulated network by one hour, run the detection
pipeline on the PUBLIC network state, publish the results. Commands from
the UI (launch, reset, speed, evidence) are queued and applied between
ticks, so the simulator and detector never race.
"""

from __future__ import annotations

import copy
import queue
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..config import DetectorConfig, RuntimeConfig, SimConfig
from ..detect import DetectionEngine, DetectionResult
from ..detect.embed import make_embedder
from ..detect.types import NORMAL, ORGANIC, SWARM
from ..detect.weights import tally
from ..metrics import MetricsTracker
from ..sim import Simulator
from ..sim.swarm import LEVELS
from .insights import evidence_detail, terrain
from .protocol import clock, pack

Publish = Callable[[dict, "str | None"], None]

LEVEL_INFO = [{"level": s.level, "name": s.name, "summary": s.summary, "cost_per_identity": s.cost_per_identity}
              for s in LEVELS.values()]


@dataclass
class World:
    sim: Simulator
    engine: DetectionEngine
    metrics: MetricsTracker


class Runtime:
    def __init__(self, sim_cfg: SimConfig, det_cfg: DetectorConfig, rt_cfg: RuntimeConfig, publish: Publish) -> None:
        self.sim_cfg, self.det_cfg, self.rt_cfg = sim_cfg, det_cfg, rt_cfg
        self.publish = publish
        self.embedder = make_embedder(det_cfg.embedder)
        self.world: World | None = None
        self.world_id = 0
        self.status = "booting"
        self.progress = 0.0
        self.rate = rt_cfg.sim_rate
        self.cmds: queue.Queue = queue.Queue()
        self.lock = threading.RLock()
        self.last_result: DetectionResult | None = None
        self.last_detection: dict | None = None
        self.last_terrain: dict | None = None
        self.launches: list[dict] = []
        self.chain = None
        self._pristine: tuple | None = None
        self._stop = threading.Event()
        self._feed_rng = np.random.default_rng(1)
        self._runs = 0

    # ------------------------------------------------------------ control
    def start(self) -> None:
        threading.Thread(target=self._main, name="mirage-runtime", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def submit(self, msg: dict, client: str | None = None) -> None:
        self.cmds.put((msg, client))

    # --------------------------------------------------------------- boot
    def _build(self) -> tuple[World, DetectionResult]:
        sim = Simulator(self.sim_cfg)
        engine = DetectionEngine(self.det_cfg, self.embedder)
        world = World(sim, engine, MetricsTracker(sim.truth))
        warm = self.sim_cfg.warmup_hours
        result = None
        for h in range(warm):
            sim.step()
            if h % 6 == 5 or h == warm - 1:
                result = engine.run(sim.public)
            self.progress = (h + 1) / warm
            if h % 4 == 3:
                self.publish({"type": "status", "status": "warming", "progress": round(self.progress, 3)}, None)
        assert result is not None
        return world, result

    def _main(self) -> None:
        try:
            self.status = "warming"
            self.publish({"type": "status", "status": "warming", "progress": 0.0}, None)
            world, result = self._build()
            self._pristine = copy.deepcopy((world, result), {id(self.embedder): self.embedder})
            with self.lock:
                self._install(world, result)
            self.status = "live"
            self.publish(self.snapshot(), None)
            self._loop()
        except Exception:  # keep the process alive and tell the UI
            self.status = "error"
            traceback.print_exc()
            self.publish({"type": "status", "status": "error"}, None)

    def _install(self, world: World, result: DetectionResult) -> None:
        self.world = world
        self.world_id += 1
        self.launches = []
        self._runs = 0
        self._on_detection(result)

    # --------------------------------------------------------------- loop
    def _loop(self) -> None:
        next_at = time.perf_counter()
        while not self._stop.is_set():
            self._drain()
            if self.rate <= 0:
                time.sleep(0.05)
                next_at = time.perf_counter()
                continue
            with self.lock:
                msgs = self._tick()
            for msg in msgs:
                self.publish(msg, None)
            next_at += 1.0 / self.rate
            delay = next_at - time.perf_counter()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_at = time.perf_counter()

    def _drain(self) -> None:
        while True:
            try:
                msg, client = self.cmds.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle(msg, client)
            except Exception:
                traceback.print_exc()

    def _handle(self, msg: dict, client: str | None) -> None:
        kind = msg.get("type")
        if kind == "launch":
            size = int(np.clip(int(msg.get("size", 1000)), 100, self.rt_cfg.max_swarm))
            level = int(np.clip(int(msg.get("level", 3)), 1, 5))
            with self.lock:
                sim = self.world.sim
                op = sim.launch_swarm(size, level)
                info = {"swarm": op.id, "level": level, "size": size, "proposal": op.proposal.id,
                        "t": op.t_launch, "clock": clock(op.t_launch), "name": LEVELS[level].name,
                        "cost_per_identity": LEVELS[level].cost_per_identity}
                self.launches.append(info)
            self.publish({"type": "launched", **info}, None)
        elif kind == "reset":
            if self._pristine is None:
                return
            with self.lock:
                world, result = copy.deepcopy(self._pristine, {id(self.embedder): self.embedder})
                self._install(world, result)
            self.publish(self.snapshot(), None)
        elif kind == "speed":
            self.rate = float(np.clip(float(msg.get("rate", 1.0)), 0.0, 8.0))
            self.publish({"type": "speed", "rate": self.rate}, None)
        elif kind == "evidence":
            with self.lock:
                detail = self._evidence(int(msg.get("cluster", -1)))
            if detail is not None:
                self.publish(detail, client)
        elif kind == "weight_mode":
            mode = "log" if msg.get("mode") == "log" else "one"
            with self.lock:
                self.world.engine.cfg.weight_mode = mode
        elif kind == "ping":
            self.publish({"type": "pong", "t": msg.get("t")}, client)

    # --------------------------------------------------------------- tick
    def _tick(self) -> list[dict]:
        world = self.world
        sim, engine = world.sim, world.engine
        posts0 = sim.net.n_posts
        summary = sim.step()
        msgs = [self._tick_msg(summary, posts0)]
        if sim.tick % self.rt_cfg.detect_every == 0:
            result = engine.run(sim.public)
            msgs.extend(self._on_detection(result))
        return msgs

    def _on_detection(self, result: DetectionResult) -> list[dict]:
        world = self.world
        world.metrics.update(result)
        self.last_result = result
        self._runs += 1
        self.last_detection = self._detection_msg(result)
        out = [self.last_detection]
        if self._runs % 2 == 1 or self.last_terrain is None:
            self.last_terrain = terrain(world.engine, result)
            out.append(self.last_terrain)
        if self.chain is not None:
            self.chain.on_detection(result, world.sim.net)
        return out

    # ------------------------------------------------------------ messages
    def _proposals(self) -> list[dict]:
        sim = self.world.sim
        net = sim.net
        weights = self.last_result.weights if self.last_result is not None else None
        out = []
        for p in sorted(net.proposals.values(), key=lambda p: p.id):
            if p.id < 5 or net.now > p.closes_at + 48 * 60:
                continue
            naive = tally(net, p.id)
            w = tally(net, p.id, weights) if weights is not None else naive
            out.append({"id": p.id, "title": p.title, "recipient": p.recipient, "amount": p.amount,
                        "created_at": p.created_at, "closes_at": p.closes_at, "open": p.is_open(net.now),
                        "naive": {"yes": naive["yes"], "no": naive["no"]},
                        "weighted": {"yes": w["yes"], "no": w["no"]},
                        "votes": naive["n_yes"] + naive["n_no"]})
        return out

    def _feed(self, posts0: int) -> list[dict]:
        net = self.world.sim.net
        n_new = net.n_posts - posts0
        if n_new <= 0:
            return []
        picks = np.sort(self._feed_rng.choice(np.arange(posts0, net.n_posts), size=min(6, n_new), replace=False))
        ac = self.last_result.account_cluster if self.last_result is not None else np.zeros(0, dtype=np.int64)
        verdict = {c.id: c.verdict for c in self.last_result.clusters} if self.last_result is not None else {}
        out = []
        for pid in picks.tolist():
            a = int(net.post_author[pid])
            cid = int(ac[a]) if a < len(ac) else -1
            out.append({"post": pid, "account": a, "handle": net.handles[a], "text": net.post_text[pid][:220],
                        "t": float(net.post_t[pid]), "reply": int(net.post_parent[pid]) >= 0,
                        "verdict": verdict.get(cid, NORMAL) if cid >= 0 else None})
        return out

    def _tick_msg(self, summary, posts0: int) -> dict:
        sim = self.world.sim
        net = sim.net
        return {
            "type": "tick", "world": self.world_id, "tick": sim.tick, "t": sim.t, "clock": clock(sim.t),
            "n_accounts": net.n_accounts,
            "new_from": int(summary.new_accounts[0]) if len(summary.new_accounts) else net.n_accounts,
            "new_created": net.acct_created.a[summary.new_accounts].round(2).tolist(),
            "active": pack(summary.active, "i4"),
            "counts": {"events": net.n_events, "posts": net.n_posts, "tick_events": summary.n_events,
                       "tick_posts": summary.n_posts, "tick_votes": summary.n_votes},
            "feed": self._feed(posts0),
            "proposals": self._proposals(),
            "rate": self.rate,
        }

    def _metrics(self, result: DetectionResult) -> dict:
        m = self.world.metrics.summary(result)
        return {k: m[k] for k in ("precision", "recall", "f1", "hard_negative_fp", "flagged", "tp", "fp", "fn",
                                  "detection_latency_min", "pipeline_latency_ms")}

    def _detection_msg(self, result: DetectionResult) -> dict:
        shown = []
        for c in result.clusters:
            watch = c.verdict == NORMAL and c.confidence >= 0.3 and c.size >= 15
            if c.verdict in (SWARM, ORGANIC) or watch:
                d = c.to_dict(with_members=False)
                d["members"] = pack(c.members, "i4")
                d["watch"] = bool(watch)
                shown.append(d)
            if len(shown) >= 48:
                break
        return {
            "type": "detection", "world": self.world_id, "run": result.run, "t": result.t, "clock": clock(result.t),
            "latency_ms": result.latency_ms, "stages": result.stages, "n_accounts": result.n_accounts,
            "n_active": result.n_active, "n_candidates": result.n_candidates, "embedder": result.embedder,
            "knn": result.knn_backend, "clusters": shown,
            "edges": {"i": pack(result.edge_i, "i4"), "j": pack(result.edge_j, "i4"), "w": pack(result.edge_w, "f4"),
                      "bits": pack(result.edge_bits, "u1")},
            "metrics": self._metrics(result),
            "weight_mode": self.world.engine.cfg.weight_mode,
        }

    def _evidence(self, cid: int) -> dict | None:
        result = self.last_result
        if result is None:
            return None
        cluster = next((c for c in result.clusters if c.id == cid), None)
        if cluster is None:
            return None
        return evidence_detail(cluster, self.world.engine, result, self.world.sim.net)

    def _activity_levels(self) -> np.ndarray:
        store = self.world.engine.store
        act = store.act[: store.n].sum(axis=1)
        lvl = np.log1p(act) / np.log1p(max(1.0, float(np.percentile(act, 99.5)) if len(act) else 1.0))
        return (np.clip(lvl, 0, 1) * 255).astype(np.uint8)

    # ---------------------------------------------------------------- views
    def hello(self) -> dict:
        return {"type": "hello", "status": self.status, "progress": self.progress, "levels": LEVEL_INFO,
                "rate": self.rate, "tick_minutes": self.sim_cfg.tick_minutes, "embedder": self.embedder.name,
                "max_swarm": self.rt_cfg.max_swarm, "chain": self.chain.info() if self.chain else None}

    def snapshot(self) -> dict:
        with self.lock:
            if self.world is None:
                return {"type": "status", "status": self.status, "progress": self.progress}
            sim = self.world.sim
            net = sim.net
            return {
                "type": "snapshot", "world": self.world_id, "status": self.status, "tick": sim.tick, "t": sim.t,
                "clock": clock(sim.t), "rate": self.rate,
                "accounts": {"n": net.n_accounts, "created": pack(net.acct_created.a, "f4"),
                             "activity": pack(self._activity_levels(), "u1")},
                "proposals": self._proposals(),
                "detection": self.last_detection,
                "terrain": self.last_terrain,
                "launches": self.launches,
                "levels": LEVEL_INFO,
                "chain": self.chain.info() if self.chain else None,
            }
