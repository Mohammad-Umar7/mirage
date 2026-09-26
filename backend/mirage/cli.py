"""Headless command line: run scenarios and print a report.

    python -m mirage.cli run --level 3 --size 1000
    python -m mirage.cli sweep --levels 1-5
    python -m mirage.cli bench --real 5000
    python -m mirage.cli llm-cache
"""

from __future__ import annotations

import argparse
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOLD, RED, DIM, BOLD, RESET = "\033[38;5;214m", "\033[38;5;203m", "\033[2m", "\033[1m", "\033[0m"


def _fmt(v, pct: bool = False) -> str:
    if v is None:
        return "  —  "
    return f"{v * 100:5.1f}%" if pct else f"{v:.3f}"


def _levels(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def _report(rep, elapsed: float, verbose: bool = True) -> None:
    m = rep.metrics
    lat = m.get("detection_latency_min")
    lvl = f"L{rep.level}" if rep.level else "no swarm"
    print(f"\n{BOLD}{GOLD}MIRAGE{RESET}  {lvl} · {rep.size if rep.level else 0:,} swarm accounts · "
          f"{rep.n_real:,} real accounts · {elapsed:.0f}s wall")
    print(f"  precision {_fmt(m['precision'], True)}   recall {_fmt(m['recall'], True)}   "
          f"F1 {_fmt(m['f1'])}   hard-negative FP {m['hard_negative_fp']}")
    print(f"  detection latency {('%.0f sim-min' % lat) if lat is not None else 'not detected'}   "
          f"pipeline p50 {rep.p50_ms:.0f} ms · p95 {rep.p95_ms:.0f} ms   "
          f"({rep.result.embedder} embeddings, {rep.result.knn_backend} kNN)")
    if not verbose:
        return
    shown = [c for c in rep.result.clusters if c.verdict == "SWARM"]
    shown += sorted((c for c in rep.result.clusters if c.verdict == "ORGANIC COMMUNITY"), key=lambda c: -c.size)[:3]
    for c in shown:
        color = RED if c.verdict == "SWARM" else GOLD
        lvl_est = f" · EST. LEVEL {c.level_estimate}" if c.level_estimate else ""
        print(f"  {color}{c.verdict}{RESET} #{c.id} · {c.size:,} accounts · confidence {c.confidence:.2f}{lvl_est}")
        for e in c.evidence[:7]:
            print(f"      {DIM}{e.title:<28}{RESET} {e.text}")


def cmd_run(args) -> None:
    from .scenario import run_scenario

    t = time.perf_counter()
    rep = run_scenario(n_real=args.real, level=args.level, size=args.size, warmup_h=args.warmup, after_h=args.hours,
                       seed=args.seed, detect_every=args.every)
    _report(rep, time.perf_counter() - t)
    print(f"\n  {DIM}timeline (hours after launch → flagged accounts):{RESET} " +
          " ".join(f"{r['hour']}h:{r['flagged']}" for r in rep.timeline[:: max(1, len(rep.timeline) // 12)]))


def cmd_sweep(args) -> None:
    from .scenario import run_scenario

    rows = []
    for level in _levels(args.levels):
        t = time.perf_counter()
        rep = run_scenario(n_real=args.real, level=level, size=args.size, warmup_h=args.warmup, after_h=args.hours,
                           seed=args.seed, detect_every=args.every)
        rows.append((level, rep, time.perf_counter() - t))
        _report(rep, rows[-1][2], verbose=args.verbose)
    print(f"\n{BOLD}level  precision  recall   F1     HN-FP  latency     p50 ms{RESET}")
    for level, rep, _ in rows:
        m = rep.metrics
        lat = m.get("detection_latency_min")
        print(f"  L{level}   {_fmt(m['precision'], True)}    {_fmt(m['recall'], True)}  {_fmt(m['f1'])}  "
              f"{m['hard_negative_fp']:>5}  {('%.0f min' % lat) if lat is not None else '    —   ':>9}  {rep.p50_ms:7.0f}")


def cmd_bench(args) -> None:
    import numpy as np

    from .config import DetectorConfig, SimConfig
    from .detect import DetectionEngine
    from .sim import Simulator

    sim = Simulator(SimConfig(seed=args.seed, n_real=args.real, use_llm_cache=False))
    engine = DetectionEngine(DetectorConfig())
    for h in range(args.warmup):
        sim.step()
        if h % 6 == 5:
            engine.run(sim.public)
    if args.level:
        sim.launch_swarm(args.size, args.level)
    lat, stages = [], []
    for _ in range(args.runs):
        sim.step()
        res = engine.run(sim.public)
        lat.append(res.latency_ms)
        stages.append(res.stages)
    print(f"{BOLD}accounts {sim.net.n_accounts:,}{RESET} · runs {args.runs} · p50 {np.median(lat):.0f} ms · "
          f"p95 {np.percentile(lat, 95):.0f} ms · max {max(lat):.0f} ms ({res.embedder}, {res.knn_backend})")
    for key in stages[-1]:
        print(f"  {key:<12} {np.median([s[key] for s in stages]):8.1f} ms")


def cmd_llm_cache(args) -> None:
    from .sim.llm import build_cache

    build_cache(per_prompt=args.per_prompt)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="mirage", description="MIRAGE headless runner")
    p.add_argument("--embedder", default=None, help="auto | minilm | hashing")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, level_default):
        sp.add_argument("--real", type=int, default=3000)
        sp.add_argument("--size", type=int, default=1000)
        sp.add_argument("--warmup", type=int, default=72)
        sp.add_argument("--hours", type=int, default=36)
        sp.add_argument("--seed", type=int, default=7)
        sp.add_argument("--every", type=int, default=2, help="detect every N ticks")
        if level_default is not None:
            sp.add_argument("--level", type=int, default=level_default)

    r = sub.add_parser("run", help="one scenario with a full report")
    common(r, 3)
    s = sub.add_parser("sweep", help="levels side by side")
    common(s, None)
    s.add_argument("--levels", default="1-5")
    s.add_argument("--verbose", action="store_true")
    b = sub.add_parser("bench", help="pipeline latency")
    common(b, 3)
    b.add_argument("--runs", type=int, default=12)
    c = sub.add_parser("llm-cache", help="pre-generate persona posts with Groq/Gemini")
    c.add_argument("--per-prompt", type=int, default=20)
    args = p.parse_args(argv)
    if args.embedder:
        os.environ["MIRAGE_EMBEDDER"] = args.embedder
    {"run": cmd_run, "sweep": cmd_sweep, "bench": cmd_bench, "llm-cache": cmd_llm_cache}[args.cmd](args)


if __name__ == "__main__":
    main()
