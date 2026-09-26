"""The detector must never be able to see ground-truth labels.

Four independent checks:
1. static   - no detection module imports simulator internals, metrics or
              truth, or even mentions label names;
2. object graph - nothing reachable from the public NetworkState is a
              GroundTruth, a hidden profile table or a swarm operator;
3. trap     - a tripwire on the GroundTruth object records every attribute
              access while the detector runs: there must be none;
4. invariance - scrambling every label after the simulation does not change
              a single detection output.
"""

from __future__ import annotations

import ast
import gc
from pathlib import Path

import numpy as np

from mirage.config import DetectorConfig, SimConfig
from mirage.detect import DetectionEngine
from mirage.network import NetworkState
from mirage.sim import Simulator
from mirage.sim.profiles import Profiles
from mirage.sim.swarm import SwarmOperator
from mirage.sim.truth import GroundTruth

DETECT_DIR = Path(__file__).resolve().parents[1] / "mirage" / "detect"
FORBIDDEN_PACKAGES = ("sim", "metrics", "scenario")
FORBIDDEN_NAMES = ("truth", "is_swarm", "groundtruth", "swarm_id", "hard_negative")


def _small_world(seed: int = 3) -> Simulator:
    sim = Simulator(SimConfig(seed=seed, n_real=600, use_llm_cache=False))
    sim.run_hours(12)
    sim.launch_swarm(120, 2)
    sim.run_hours(8)
    return sim


def _forbidden(module: str) -> bool:
    head = module.split(".")[0]
    return head in FORBIDDEN_PACKAGES


def test_detect_modules_never_import_labels_or_simulator():
    offenders = []
    for path in DETECT_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level == 0 and module.startswith("mirage.") and _forbidden(module[len("mirage."):]):
                    offenders.append(f"{path.name}: from {module} import ...")
                elif node.level >= 2 and _forbidden(module):  # from ..sim / ..metrics
                    offenders.append(f"{path.name}: from {'.' * node.level}{module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("mirage.") and _forbidden(alias.name[len("mirage."):]):
                        offenders.append(f"{path.name}: import {alias.name}")
    assert not offenders, offenders


def test_detect_modules_never_mention_label_names():
    offenders = []
    for path in DETECT_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Name):
                names.append(node.id)
            elif isinstance(node, ast.Attribute):
                names.append(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names.append(node.name)
            elif isinstance(node, ast.arg):
                names.append(node.arg)
            for name in names:
                low = name.lower()
                if any(f in low for f in FORBIDDEN_NAMES):
                    offenders.append(f"{path.name}:{getattr(node, 'lineno', '?')}: {name}")
    assert not offenders, offenders


def _reachable(root, limit: int = 2_000_000):
    """Every object reachable from root via references (bounded BFS)."""
    seen: set[int] = set()
    stack = [root]
    while stack and len(seen) < limit:
        obj = stack.pop()
        if id(obj) in seen or isinstance(obj, (type, type(gc))):
            continue
        seen.add(id(obj))
        yield obj
        if isinstance(obj, (str, bytes, int, float, bool, np.ndarray, np.generic)):
            continue
        stack.extend(gc.get_referents(obj))


def test_public_state_cannot_reach_hidden_state():
    sim = _small_world()
    public = sim.public
    assert isinstance(public, NetworkState)
    hidden_types = (GroundTruth, Profiles, SwarmOperator, Simulator)
    for obj in _reachable(public):
        assert not isinstance(obj, hidden_types), f"public state reaches {type(obj).__name__}"
        if isinstance(obj, dict):
            for key in obj:
                if isinstance(key, str):
                    assert "swarm" not in key.lower() and "truth" not in key.lower(), key


class _Tripwire:
    """Wraps GroundTruth and records every attribute access."""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "touched", [])

    def __getattr__(self, name):
        object.__getattribute__(self, "touched").append(name)
        return getattr(object.__getattribute__(self, "_inner"), name)


def test_detector_never_touches_truth_while_running():
    sim = _small_world()
    wire = _Tripwire(sim.truth)
    sim.truth = wire  # anything that read labels during detection would trip this
    engine = DetectionEngine(DetectorConfig())
    engine.run(sim.public)
    engine.run(sim.public)
    assert wire.touched == []


def test_scrambled_labels_do_not_change_detection():
    def detect(scramble: bool):
        sim = _small_world(seed=5)
        if scramble:
            rng = np.random.default_rng(0)
            kind = sim.truth.kind.a
            kind[:] = rng.permutation(kind)
            for rec in sim.truth.swarms.values():
                rec.members = list(rng.choice(sim.net.n_accounts, size=len(rec.members), replace=False))
        engine = DetectionEngine(DetectorConfig())
        for _ in range(3):
            res = engine.run(sim.public)
        return res

    a, b = detect(False), detect(True)
    assert [c.members.tolist() for c in a.clusters] == [c.members.tolist() for c in b.clusters]
    assert [round(c.confidence, 9) for c in a.clusters] == [round(c.confidence, 9) for c in b.clusters]
    assert [c.verdict for c in a.clusters] == [c.verdict for c in b.clusters]
    assert np.array_equal(a.weights, b.weights)
