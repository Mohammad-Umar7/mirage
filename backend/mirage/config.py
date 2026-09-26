"""Configuration for the simulator, the detector and the live runtime."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = BACKEND_ROOT / ".cache"


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (KEY=VALUE lines); never overrides real env vars."""
    path = path or REPO_ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _coerce(kind, raw: str):
    if kind is bool or kind == "bool":
        return raw.lower() in ("1", "true", "yes", "on")
    if kind is int or kind == "int":
        return int(raw)
    if kind is float or kind == "float":
        return float(raw)
    return raw


class _EnvMixin:
    ENV_PREFIX = "MIRAGE_"
    ENV_MAP: dict[str, str] = {}

    @classmethod
    def from_env(cls, **overrides):
        load_dotenv()
        values = {}
        for f in fields(cls):
            env_name = cls.ENV_MAP.get(f.name, cls.ENV_PREFIX + f.name.upper())
            if env_name in os.environ:
                values[f.name] = _coerce(f.type, os.environ[env_name])
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SimConfig(_EnvMixin):
    """Network simulator knobs. Defaults are the demo configuration."""

    ENV_MAP = {"n_real": "MIRAGE_REAL_ACCOUNTS", "seed": "MIRAGE_SEED"}

    seed: int = 7
    n_real: int = 3000
    tick_minutes: float = 60.0
    warmup_hours: int = 72
    history_days: int = 365
    join_rate_per_day: float = 36.0
    news_every_hours: float = 4.0
    club_size: int = 40
    friend_group_size: int = 12
    working_group_size: int = 24
    proposal_vote_hours: float = 120.0
    real_turnout: float = 0.32
    attack_yes_rate: float = 0.08
    use_llm_cache: bool = True


@dataclass
class DetectorConfig(_EnvMixin):
    """Detection engine knobs.

    Nothing in here is fitted to ground truth at runtime; thresholds are
    fixed design choices documented in README (How detection works).
    """

    window_hours: float = 96.0
    bin_minutes: float = 15.0
    smooth_bins: float = 1.5
    knn_k: int = 10
    candidate_z: float = 3.75
    min_events: int = 3
    min_timing_events: int = 4
    min_posts: int = 2
    timing_dims: int = 64
    content_dims: int = 96
    posts_per_account: int = 8
    style_posts_per_account: int = 12
    behavior_dims: int = 48
    funding_hops: int = 4
    hub_min_recipients: int = 150
    hub_min_span_days: float = 10.0
    z_floor: float = 3.0
    z_full: float = 6.0
    single_signal_factor: float = 0.25
    min_edge_weight: float = 0.3
    min_community: int = 5
    swarm_threshold: float = 0.6
    flag_threshold: float = 0.8
    weight_mode: str = "one"
    embed_budget: int = 4096
    embedder: str = "auto"
    baseline_alpha: float = 0.08
    maturity_hours: float = 24.0
    viz_edges: int = 12000
    seed: int = 0


@dataclass
class RuntimeConfig(_EnvMixin):
    """Live server knobs."""

    ENV_MAP = {"sim_rate": "MIRAGE_SIM_RATE", "api_port": "MIRAGE_API_PORT", "chain_port": "MIRAGE_CHAIN_PORT"}

    sim_rate: float = 1.0          # simulated hours per real second
    detect_every: int = 1          # run detection every N ticks
    api_port: int = 8000
    chain_port: int = 8545
    chain_enabled: bool = True
    max_swarm: int = 10000
