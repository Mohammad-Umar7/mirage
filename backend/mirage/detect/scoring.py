"""Score communities against how real communities in this network look.

Every family of evidence is turned into a strength in [0, 1]. Mechanical
families (timing, style, scripted behaviour, funding, voting, latency,
lifecycle) are what a single operator leaks; interest families (shared
topics, social ties) are what real communities share. A SWARM verdict
needs independent corroboration: at least two strong mechanical families,
at least one of which is behavioural.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from ..network import NetworkState
from ..util import mean_pairwise_cosine, min_window, ramp, ramp_down_log
from .baseline import Baseline
from .features import ACTION_NAME, FeatureStore
from .signals import DenseSignal, _sessions
from .types import NORMAL, ORGANIC, SWARM

DAY = 1440.0
WEIGHTS = {"sync": 0.6, "style": 0.55, "behavior": 0.5, "funding": 0.65, "vote": 0.55, "latency": 0.35,
           "lifecycle": 0.45}
BEHAVIORAL = ("sync", "style", "behavior", "vote", "latency")
COORDINATION = ("sync", "funding", "vote", "latency", "lifecycle")
VECTOR_KEYS = (("timing", "sync"), ("content", "content"), ("style", "style"), ("behavior", "behavior"))


@dataclass
class ScoringContext:
    dense: dict[str, DenseSignal]
    fview: dict
    store: FeatureStore
    net: NetworkState
    now: float
    latency_cache: dict[int, float]

    def latency_of(self, a: int) -> float:
        v = self.latency_cache.get(a)
        if v is None:
            cutoff = self.now - self.store.window
            vals = sorted(x for t, x in self.store.latency[a] if t >= cutoff and x >= 0)
            if vals:
                mid = len(vals) // 2
                v = vals[mid] if len(vals) % 2 else 0.5 * (vals[mid - 1] + vals[mid])
            else:
                v = float("nan")
            self.latency_cache[a] = v
        return v


def _nan() -> float:
    return float("nan")


def group_metrics(members: np.ndarray, ctx: ScoringContext, full: bool = True) -> dict:
    members = np.asarray(members, dtype=np.int64)
    n = len(members)
    m: dict = {"size": n}
    for sig_name, key in VECTOR_KEYS:
        sig = ctx.dense.get(sig_name)
        V = sig.vectors(members) if sig is not None else np.zeros((0, 1), dtype=np.float32)
        m[key] = mean_pairwise_cosine(V) if len(V) >= 3 else _nan()
        m[f"{key}_cov"] = len(V) / max(1, n)

    fv = ctx.fview
    roots, hops = fv["root"][members], fv["root_hops"][members]
    ft, hub = fv["first_t"][members], fv["first_hub"][members]
    funded = np.isfinite(ft)
    m["fund_funded_frac"] = float(funded.mean()) if n else 0.0
    m["fund_hub_frac"] = float((hub >= 0).mean()) if n else 0.0
    m["fund_window_all"] = min_window(ft[funded]) if funded.sum() >= 3 else _nan()
    m["fund_shared_frac"] = 0.0
    rooted = roots >= 0
    if rooted.any():
        vals, counts = np.unique(roots[rooted], return_counts=True)
        min_share = max(3, int(np.ceil(0.05 * n)))
        big = counts >= min_share
        if big.any():
            shared = np.isin(roots, vals[big])
            m["fund_shared_frac"] = float(shared.mean())
            m["fund_shared_n"] = int(shared.sum())
            c_sorted = np.sort(counts[big])[::-1]
            cum = np.cumsum(c_sorted) / c_sorted.sum()
            m["fund_roots90"] = int(np.searchsorted(cum, 0.9 - 1e-9) + 1)
            m["fund_max_hops"] = int(hops[shared].max())
            sh_t = ft[shared & funded]
            m["fund_window"] = min_window(sh_t) if len(sh_t) >= 3 else _nan()
    if (hub >= 0).sum() >= 3:
        hv, hc = np.unique(hub[hub >= 0], return_counts=True)
        top = int(hv[np.argmax(hc)])
        m["fund_top_hub"] = top
        m["fund_top_hub_frac"] = float(hc.max() / n)

    created = ctx.store.created[members]
    m["created_window"] = min_window(created)
    fa = ctx.store.first_action[members]
    ok = np.isfinite(fa)
    m["activation_window"] = min_window(fa[ok]) if ok.sum() >= 3 else _nan()
    m["activation_delay"] = float(np.median(fa[ok] - created[ok])) if ok.any() else _nan()
    m["age_days"] = float(np.median(ctx.now - created) / DAY)

    if not full:
        return m

    # voting: the proposal this group turned out for most
    per_pid: dict[int, list[tuple[float, int]]] = {}
    for a in members.tolist():
        for pid, (t, c) in ctx.store.votes[a].items():
            per_pid.setdefault(pid, []).append((t, c))
    best = None
    for pid, votes in per_pid.items():
        part = len(votes) / n
        if best is None or part > best[1] or (part == best[1] and pid > best[0]):
            best = (pid, part, votes)
    if best is not None:
        pid, part, votes = best
        choices = np.array([c for _, c in votes])
        yes = int((choices == 1).sum())
        maj = 1 if yes * 2 >= len(choices) else 0
        m["vote_pid"] = int(pid)
        m["vote_participation"] = float(part)
        m["vote_choice"] = maj
        m["vote_agreement"] = float(max(yes, len(choices) - yes) / len(choices))
        maj_t = np.array([t for t, c in votes if c == maj])
        m["vote_window"] = min_window(maj_t) if len(maj_t) >= 3 else _nan()
        member_set = set(members.tolist())
        others = np.array([t for t, a in ctx.store.proposal_votes.get(pid, ()) if a not in member_set])
        m["vote_ref_window"] = min_window(others) if len(others) >= 10 else _nan()

    lats = np.array([ctx.latency_of(a) for a in members[:600].tolist()])
    lats = lats[np.isfinite(lats)]
    m["latency_n"] = int(len(lats))
    m["latency_med"] = float(np.median(lats)) if len(lats) else _nan()

    sample = members if n <= 150 else members[np.linspace(0, n - 1, 150).astype(np.int64)]
    sset = set(sample.tolist())
    links = sum(len(ctx.store.follows[a] & sset) for a in sample.tolist())
    m["follow_density"] = links / max(1, len(sample) * (len(sample) - 1))
    return m


def session_script(members: np.ndarray, ctx: ScoringContext, m: dict) -> None:
    """Most common session opening (first 4 actions) among members.

    Only needed to phrase evidence, so it runs for flagged clusters only.
    """
    patterns: Counter = Counter()
    counted = 0
    for a in members[:400].tolist():
        acts = ctx.store.window_actions(a)
        sessions = [s for s in _sessions(acts) if len(s) >= 3]
        if not sessions:
            continue
        counted += 1
        seen = {tuple(s[:4]) for s in sessions}
        patterns.update(seen)
    if patterns and counted:
        pat, cnt = patterns.most_common(1)[0]
        m["script"] = " → ".join(ACTION_NAME.get(c, "?") for c in pat)
        m["script_frac"] = cnt / counted


def _ref(base: Baseline, key: str) -> float:
    """Reference for thresholds: typical random account groups.

    Detected organic communities are NOT used here: they were grouped for
    being similar, so their similarity is inflated by selection. They are
    still quoted in evidence text as context.
    """
    v = base.group.get(key)
    return v if v is not None and v == v else 0.0


def remember(s: dict[str, float], prev: dict[str, float] | None, dt_min: float,
             half_life_min: float = 24 * 60.0) -> dict[str, float]:
    """Evidence memory: a swarm caught acting in lockstep does not become
    innocent between campaign waves. Each mechanical family keeps the max of
    its current strength and its decayed previous strength."""
    if not prev:
        return s
    decay = 0.5 ** (max(0.0, dt_min) / half_life_min)
    out = dict(s)
    for fam in WEIGHTS:
        out[fam] = max(s.get(fam, 0.0), prev.get(fam, 0.0) * decay)
    return out


def strengths(m: dict, base: Baseline) -> dict[str, float]:
    s: dict[str, float] = {}
    for key in ("sync", "style", "behavior"):
        v = m.get(key, float("nan"))
        s[key] = ramp(v - _ref(base, key), 0.2, 0.5) * ramp(m.get(f"{key}_cov", 0.0), 0.3, 0.6) if v == v else 0.0
    shared = m.get("fund_shared_frac", 0.0) * (0.35 + 0.65 * ramp_down_log(m.get("fund_window", float("nan")),
                                                                            120.0, 7 * DAY))
    burst = 0.8 * ramp_down_log(m.get("fund_window_all", float("nan")), 120.0, 7 * DAY) * m.get("fund_funded_frac", 0)
    s["funding"] = max(shared, burst)
    # Lockstep = voting far tighter than everyone else who voted on the same
    # proposal (members excluded). Early in a vote every window is short, so
    # an absolute window alone would be unfair to real blocs.
    part = m.get("vote_participation", 0.0)
    window, ref = m.get("vote_window", float("nan")), m.get("vote_ref_window", float("nan"))
    if ref == ref and ref > 0 and window == window:
        tight = ramp_down_log(window / ref, 0.02, 0.4)
    else:
        tight = ramp_down_log(window, 15.0, DAY)
    voters = part * m.get("size", 0)
    s["vote"] = ramp(part, 0.3, 0.7) * ramp(m.get("vote_agreement", 0.0), 0.75, 0.95) * tight *         ramp(voters, 10, 30)
    pop = base.latency_pop
    lat = m.get("latency_med", float("nan"))
    if pop and lat == lat and m.get("latency_n", 0) >= 5:
        s["latency"] = ramp(1.0 - lat / pop, 0.6, 0.95)
    else:
        s["latency"] = 0.0
    created = ramp_down_log(m.get("created_window", float("nan")), 180.0, 14 * DAY)
    sleeper = ramp_down_log(m.get("activation_window", float("nan")), 180.0, 14 * DAY) * \
        ramp(m.get("activation_delay", 0.0), 7 * DAY, 21 * DAY)
    s["lifecycle"] = max(created, sleeper)
    content = m.get("content", float("nan"))
    s["content"] = ramp(content - _ref(base, "content"), 0.1, 0.4) if content == content else 0.0
    s["social"] = ramp(m.get("follow_density", 0.0), 0.1, 0.4)
    return s


def confidence(s: dict[str, float], size: int) -> tuple[float, list[str]]:
    """Noisy-OR over mechanical families, gated on independent corroboration.

    SWARM-level confidence needs (a) two strong families, (b) one of them
    behavioural (what the accounts do), and (c) one of them a coordination
    family (shared clock, money, vote, reflexes or lifecycle). People with
    similar tastes can share a style or a topic by accident; they do not
    share a funder or a trigger.
    """
    prod = 1.0
    for fam, w in WEIGHTS.items():
        prod *= 1.0 - w * s.get(fam, 0.0)
    conf = 1.0 - prod
    strong = [f for f in WEIGHTS if s.get(f, 0.0) >= 0.5]
    behavioral = any(f in BEHAVIORAL for f in strong)
    coordinated = any(f in COORDINATION for f in strong)
    if not strong:
        conf = min(conf, 0.25)
    elif len(strong) == 1 or not behavioral or not coordinated:
        conf = min(conf, 0.45)
    conf *= ramp(size, 5, 20)  # a handful of accounts is where coincidences live
    return float(conf), strong


def verdict(conf: float, s: dict[str, float], m: dict, swarm_threshold: float, min_size: int,
            min_organic: int = 8) -> str:
    if conf >= swarm_threshold:
        return SWARM
    # Organic cohesion = shared interests or real social ties. Edge weight is
    # deliberately not used: a not-yet-active swarm is tightly wired too.
    cohesion = max(s.get("content", 0.0), s.get("social", 0.0))
    if m["size"] >= max(min_size, min_organic) and cohesion >= 0.3:
        return ORGANIC
    return NORMAL


def level_estimate(m: dict) -> int:
    shared = m.get("fund_shared_frac", 0.0)
    hops = m.get("fund_max_hops", 0)
    if m.get("content", 0.0) >= 0.9 and shared >= 0.5 and m.get("fund_roots90", 9) <= 1 and hops <= 1:
        return 1
    if shared >= 0.5 and hops <= 2:
        return 2
    if shared >= 0.5:
        return 3
    if m.get("activation_delay", 0.0) >= 7 * DAY:
        return 4
    if m.get("created_window", float("inf")) <= DAY:
        return 3
    return 4
