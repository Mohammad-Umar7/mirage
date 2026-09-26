"""Hidden per-account behaviour parameters (rhythm, rate, interests, style).

These are generative parameters of the simulation, not observations: the
detector never sees them, it only sees the events they produce.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..util import Growable2D, GrowableArray
from .style import StyleProfile, sample_style
from .topics import ALL_TOPIC_KEYS

TOPIC_INDEX = {k: i for i, k in enumerate(ALL_TOPIC_KEYS)}
N_TOPICS = len(ALL_TOPIC_KEYS)
GENERAL_TOPICS = np.array([TOPIC_INDEX[k] for k in ALL_TOPIC_KEYS if k != "campus"])

TZ_CHOICES = np.array([-8.0, -5.0, -3.0, 0.0, 1.0, 3.0, 5.5, 8.0, 9.0], dtype=np.float32)
TZ_WEIGHTS = np.array([0.14, 0.2, 0.05, 0.13, 0.16, 0.05, 0.09, 0.12, 0.06])
TZ_WEIGHTS = TZ_WEIGHTS / TZ_WEIGHTS.sum()

# post, reply, follow, transfer
MIX_ALPHA = np.array([4.5, 3.0, 1.5, 0.45])


def _circular_gauss(h: np.ndarray, mu: float, sd: float) -> np.ndarray:
    d = np.abs(((h - mu) + 12.0) % 24.0 - 12.0)
    return np.exp(-0.5 * (d / sd) ** 2)


def circadian_curve(shift: float, peakiness: float, night_owl: float = 0.0) -> np.ndarray:
    """Hourly activity propensity over LOCAL hours 0..23, mean 1."""
    h = np.arange(24, dtype=np.float64)
    curve = (
        0.05
        + 0.55 * _circular_gauss(h, 9.5 + shift, 1.8)
        + 0.5 * _circular_gauss(h, 13.0 + shift, 1.5)
        + 1.0 * _circular_gauss(h, 20.5 + shift + night_owl, 2.4)
        + 0.35 * night_owl * _circular_gauss(h, 1.0 + shift, 1.5)
    )
    curve = curve**peakiness
    return (curve / curve.mean()).astype(np.float32)


@dataclass
class ProfileDraft:
    tz: float
    rate: float
    circ: np.ndarray
    interest: np.ndarray
    mix: np.ndarray
    turnout: float
    style: StyleProfile


def sample_rate(rng: np.random.Generator) -> float:
    """Events per day; heavy-tailed (power law) like real social networks."""
    return float(np.clip(0.8 * (1.0 + rng.pareto(1.25)), 0.3, 80.0))


def sample_interest(rng: np.random.Generator, concentration: float = 0.35) -> np.ndarray:
    vec = np.zeros(N_TOPICS, dtype=np.float32)
    vec[GENERAL_TOPICS] = rng.dirichlet(np.full(len(GENERAL_TOPICS), concentration))
    return vec


def sample_real(rng: np.random.Generator, tz: float | None = None) -> ProfileDraft:
    if tz is None:
        tz = float(rng.choice(TZ_CHOICES, p=TZ_WEIGHTS))
    return ProfileDraft(
        tz=tz,
        rate=sample_rate(rng),
        circ=circadian_curve(float(rng.normal(0, 1.4)), float(rng.uniform(0.8, 1.6)),
                             float(rng.uniform(0, 1.5)) if rng.random() < 0.25 else 0.0),
        interest=sample_interest(rng),
        mix=rng.dirichlet(MIX_ALPHA).astype(np.float32),
        turnout=float(rng.beta(2.0, 4.0)),
        style=sample_style(rng),
    )


class Profiles:
    """Column store of hidden behaviour parameters, indexed by account."""

    def __init__(self) -> None:
        self.tz = GrowableArray(np.float32)
        self.rate = GrowableArray(np.float32)
        self.circ = Growable2D(np.float32, 24)
        self.interest = Growable2D(np.float32, N_TOPICS)
        self.mix = Growable2D(np.float32, 4)
        self.turnout = GrowableArray(np.float32)
        self.boost = GrowableArray(np.float32)
        self.boost_until = GrowableArray(np.float64)
        self.style: list[StyleProfile] = []
        # None for people writing in their own voice, otherwise the swarm
        # operator whose generator writes for this account.
        self.writer: list[object | None] = []
        self.persona: list[str] = []

    def add(self, d: ProfileDraft, writer: object | None = None, persona: str = "") -> int:
        idx = self.tz.append(d.tz)
        self.rate.append(d.rate)
        self.circ.append(d.circ)
        self.interest.append(d.interest)
        self.mix.append(d.mix)
        self.turnout.append(d.turnout)
        self.boost.append(1.0)
        self.boost_until.append(-1e18)
        self.style.append(d.style)
        self.writer.append(writer)
        self.persona.append(persona)
        return idx

    def __len__(self) -> int:
        return self.tz.n
