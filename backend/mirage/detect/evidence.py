"""Plain-language evidence, with numbers, for every verdict."""

from __future__ import annotations

from ..network import NetworkState
from ..util import fmt_duration, fmt_span
from .baseline import Baseline
from .types import ORGANIC, SWARM, Evidence

DAY = 1440.0


def _pct(x: float) -> str:
    return f"{round(100 * x)}%"


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _hub_name(net: NetworkState, wallet: int) -> str:
    label = net.wallet_label[wallet] if 0 <= wallet < len(net.wallet_label) else None
    return label.split("·")[-1].strip() if label else "one exchange"


def build_evidence(verdict: str, m: dict, s: dict[str, float], base: Baseline, net: NetworkState) -> list[Evidence]:
    if verdict == SWARM:
        return _swarm(m, s, base, net)
    if verdict == ORGANIC:
        return _organic(m, s, base)
    return []


def _ref(base: Baseline, key: str) -> tuple[float, str]:
    """Reference quoted in evidence text.

    Timing is compared with the real communities the detector found (they
    are the fair comparison: real groups, human clocks). Similarity families
    are compared with typical accounts, because found communities were
    grouped *for* being similar and would flatter the comparison.
    """
    if key == "sync":
        return base.reference(key)
    val = base.group.get(key)
    return (val, "typical accounts") if val is not None else base.reference(key)


def _swarm(m: dict, s: dict[str, float], base: Baseline, net: NetworkState) -> list[Evidence]:
    ev: list[Evidence] = []
    size = int(m["size"])

    # --- funding
    if m.get("fund_shared_frac", 0) >= 0.3 and "fund_roots90" in m:
        n_shared = int(m.get("fund_shared_n", 0))
        roots = int(m["fund_roots90"])
        hops = int(m.get("fund_max_hops", 1))
        text = f"{n_shared:,} accounts trace funding to {_plural(roots, 'wallet')} within {_plural(hops, 'hop')}"
        win = m.get("fund_window", float("nan"))
        if win == win:
            text += f"; 90% were funded inside {fmt_span(win)}"
        ev.append(Evidence("funding", "SHARED FUNDING", text, m["fund_shared_frac"], None, s["funding"]))
    elif m.get("fund_top_hub_frac", 0) >= 0.5 and m.get("fund_window_all") == m.get("fund_window_all"):
        hub = _hub_name(net, int(m["fund_top_hub"]))
        text = (f"{_pct(m['fund_top_hub_frac'])} of accounts were first funded by {hub} withdrawals "
                f"inside one {fmt_duration(m['fund_window_all'])} window")
        ev.append(Evidence("funding", "FUNDING BURST", text, m["fund_top_hub_frac"], None, s["funding"]))

    # --- timing
    if m.get("sync") == m.get("sync") and s.get("sync", 0) > 0.05:
        ref, label = _ref(base, "sync")
        ev.append(Evidence("timing", "SYNCHRONIZED ACTIVITY",
                           f"Activity correlation {m['sync']:.2f} ({label}: {ref:.2f})", m["sync"], ref, s["sync"]))

    # --- content / style
    if m.get("content") == m.get("content"):
        ref, _ = _ref(base, "content")
        if m["content"] - ref > 0.1:
            ev.append(Evidence("content", "SEMANTIC SIMILARITY",
                               f"Post semantic similarity {m['content']:.2f} vs baseline {ref:.2f}",
                               m["content"], ref, s.get("content", 0.0)))
    if m.get("style") == m.get("style") and s.get("style", 0) > 0.05:
        ref, _ = _ref(base, "style")
        ev.append(Evidence("style", "SHARED WRITING FINGERPRINT",
                           f"Writing-style fingerprint match {m['style']:.2f} vs baseline {ref:.2f} "
                           f"(one generator behind many personas)", m["style"], ref, s["style"]))

    # --- voting
    if s.get("vote", 0) > 0.05 and "vote_pid" in m:
        choice = "YES" if m.get("vote_choice") == 1 else "NO"
        voters = round(m["vote_participation"] * size)
        text = (f"{voters:,} accounts voted {choice} on Proposal #{m['vote_pid']} within a "
                f"{fmt_duration(m['vote_window'])} window")
        ref = m.get("vote_ref_window", float("nan"))
        if ref == ref:
            text += f" (everyone else: {fmt_span(ref)})"
        ev.append(Evidence("voting", "LOCKSTEP VOTE", text, m["vote_window"], ref if ref == ref else None,
                           s["vote"]))

    # --- behaviour
    if s.get("behavior", 0) > 0.05:
        ref, _ = _ref(base, "behavior")
        text = f"Behavioral similarity {m['behavior']:.2f} vs baseline {ref:.2f}"
        if m.get("script") and m.get("script_frac", 0) >= 0.4:
            text = f"{_pct(m['script_frac'])} of accounts run the same session script: {m['script']}"
        ev.append(Evidence("behavior", "SCRIPTED SESSIONS", text, m["behavior"], ref, s["behavior"]))

    # --- lifecycle
    if s.get("lifecycle", 0) > 0.1:
        if m.get("activation_delay", 0) >= 7 * DAY and m.get("activation_window") == m.get("activation_window"):
            text = (f"{size:,} accounts sat dormant for {m['activation_delay'] / DAY:.0f}+ days, then woke up "
                    f"inside {fmt_span(m['activation_window'])}")
        else:
            text = f"90% of {size:,} accounts were created inside {fmt_span(m['created_window'])}"
        ev.append(Evidence("lifecycle", "ACCOUNT LIFECYCLE", text, m.get("created_window", 0.0), None,
                           s["lifecycle"]))

    # --- latency
    if s.get("latency", 0) > 0.05 and base.latency_pop:
        ev.append(Evidence("latency", "REACTION LATENCY",
                           f"Median reply latency {fmt_span(m['latency_med'])} vs network {fmt_span(base.latency_pop)}",
                           m["latency_med"], base.latency_pop, s["latency"]))

    ev.sort(key=lambda e: -e.strength)
    return ev


def _organic(m: dict, s: dict[str, float], base: Baseline) -> list[Evidence]:
    ev: list[Evidence] = []
    size = int(m["size"])
    if m.get("content") == m.get("content"):
        ref, _ = _ref(base, "content")
        ev.append(Evidence("content", "SHARED INTEREST",
                           f"Shared interests: post similarity {m['content']:.2f} vs baseline {ref:.2f}",
                           m["content"], ref, s.get("content", 0.0)))
    if m.get("follow_density", 0) > 0.05:
        ev.append(Evidence("social", "REAL SOCIAL TIES",
                           f"{_pct(m['follow_density'])} of member pairs follow each other",
                           m["follow_density"], None, s.get("social", 0.0)))
    roots = m.get("fund_roots90")
    if m.get("fund_shared_frac", 0.0) < 0.5:
        text = f"Independent funding: {_pct(1 - m.get('fund_shared_frac', 0.0))} of {size} accounts share no private funder"
        if m.get("fund_window_all") == m.get("fund_window_all"):
            text += f", first funds spread over {fmt_span(m['fund_window_all'])}"
        ev.append(Evidence("funding", "INDEPENDENT FUNDING", text, m.get("fund_shared_frac", 0.0), None,
                           1 - s.get("funding", 0.0)))
    elif roots:
        ev.append(Evidence("funding", "FUNDING", f"Funding traces to {_plural(int(roots), 'wallet')}",
                           float(roots), None, 1 - s.get("funding", 0.0)))
    if m.get("sync") == m.get("sync"):
        ev.append(Evidence("timing", "HUMAN TIMING", f"Human timing: activity correlation {m['sync']:.2f}",
                           m["sync"], None, 1 - s.get("sync", 0.0)))
    if m.get("style") == m.get("style"):
        ev.append(Evidence("style", "DIVERSE VOICES", f"Diverse writing styles: fingerprint match {m['style']:.2f}",
                           m["style"], None, 1 - s.get("style", 0.0)))
    if m.get("vote_participation", 0) >= 0.5 and m.get("vote_window") == m.get("vote_window"):
        ev.append(Evidence("voting", "BLOC VOTE, HUMAN PACE",
                           f"Votes together on Proposal #{m['vote_pid']} but spread over {fmt_span(m['vote_window'])}",
                           m["vote_window"], None, 1 - s.get("vote", 0.0)))
    return ev
