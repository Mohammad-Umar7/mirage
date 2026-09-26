"""Small shared helpers: growable numpy columns, ramps and formatting."""

from __future__ import annotations

import math

import numpy as np


class GrowableArray:
    """A 1-D numpy column with amortised O(1) append."""

    __slots__ = ("_data", "n", "dtype")

    def __init__(self, dtype, capacity: int = 1024):
        self.dtype = np.dtype(dtype)
        self._data = np.empty(max(16, capacity), dtype=self.dtype)
        self.n = 0

    def _reserve(self, extra: int) -> None:
        need = self.n + extra
        if need > len(self._data):
            cap = max(need, int(len(self._data) * 1.6) + 16)
            grown = np.empty(cap, dtype=self.dtype)
            grown[: self.n] = self._data[: self.n]
            self._data = grown

    def append(self, value) -> int:
        self._reserve(1)
        self._data[self.n] = value
        self.n += 1
        return self.n - 1

    def extend(self, values) -> None:
        values = np.asarray(values, dtype=self.dtype)
        self._reserve(len(values))
        self._data[self.n : self.n + len(values)] = values
        self.n += len(values)

    @property
    def a(self) -> np.ndarray:
        """View of the filled part of the column."""
        return self._data[: self.n]

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, idx):
        return self._data[: self.n][idx]

    def __setitem__(self, idx, value) -> None:
        self._data[: self.n][idx] = value


class Growable2D:
    """A 2-D numpy table (rows grow, width fixed) with amortised append."""

    __slots__ = ("_data", "n", "width", "dtype")

    def __init__(self, dtype, width: int, capacity: int = 1024):
        self.dtype = np.dtype(dtype)
        self.width = width
        self._data = np.zeros((max(16, capacity), width), dtype=self.dtype)
        self.n = 0

    def _reserve(self, extra: int) -> None:
        need = self.n + extra
        if need > len(self._data):
            cap = max(need, int(len(self._data) * 1.6) + 16)
            grown = np.zeros((cap, self.width), dtype=self.dtype)
            grown[: self.n] = self._data[: self.n]
            self._data = grown

    def append(self, row) -> int:
        self._reserve(1)
        self._data[self.n] = row
        self.n += 1
        return self.n - 1

    @property
    def a(self) -> np.ndarray:
        return self._data[: self.n]

    def __len__(self) -> int:
        return self.n


def ramp(x: float, lo: float, hi: float) -> float:
    """0 at or below lo, 1 at or above hi, linear in between."""
    if x != x:  # NaN
        return 0.0
    if hi == lo:
        return 1.0 if x >= hi else 0.0
    return float(min(1.0, max(0.0, (x - lo) / (hi - lo))))


def ramp_down_log(x: float, good: float, bad: float) -> float:
    """1 when x <= good, 0 when x >= bad, log-linear in between.

    Used for "how tight is this time window" style scores where the
    difference between 90 seconds and 10 minutes matters as much as the
    difference between 1 hour and 6 hours.
    """
    if x != x or x < 0:
        return 0.0
    x = max(x, 1e-9)
    if x <= good:
        return 1.0
    if x >= bad:
        return 0.0
    return float((math.log(bad) - math.log(x)) / (math.log(bad) - math.log(good)))


def fmt_duration(minutes: float) -> str:
    """Human friendly duration from simulated minutes."""
    if minutes != minutes:
        return "n/a"
    seconds = minutes * 60.0
    if seconds < 120:
        return f"{max(1, round(seconds))}-second"
    if minutes < 90:
        return f"{round(minutes)}-minute"
    hours = minutes / 60.0
    if hours < 48:
        whole = int(hours)
        rest = round(minutes - whole * 60)
        if rest == 60:
            whole, rest = whole + 1, 0
        return f"{whole}h {rest:02d}m" if rest else f"{whole}-hour"
    return f"{hours / 24:.1f}-day"


def fmt_span(minutes: float) -> str:
    """Duration phrased as a noun ("6 minutes", "3h 12m", "2.4 days")."""
    if minutes != minutes:
        return "n/a"
    seconds = minutes * 60.0
    if seconds < 120:
        s = max(1, round(seconds))
        return f"{s} second{'s' if s != 1 else ''}"
    if minutes < 90:
        m = round(minutes)
        return f"{m} minutes"
    hours = minutes / 60.0
    if hours < 48:
        whole = int(hours)
        rest = round(minutes - whole * 60)
        if rest == 60:
            whole, rest = whole + 1, 0
        return f"{whole}h {rest:02d}m" if rest else f"{whole} hours"
    return f"{hours / 24:.1f} days"


def min_window(times: np.ndarray, frac: float = 0.9) -> float:
    """Length of the shortest window that contains `frac` of the times."""
    times = np.sort(np.asarray(times, dtype=np.float64))
    m = len(times)
    if m == 0:
        return float("nan")
    if m == 1:
        return 0.0
    k = max(2, int(math.ceil(frac * m)))
    if k >= m:
        return float(times[-1] - times[0])
    spans = times[k - 1 :] - times[: m - k + 1]
    return float(spans.min())


def mean_pairwise_cosine(rows: np.ndarray) -> float:
    """Mean dot product over all distinct pairs of rows in O(n*d).

    sum_{i!=j} u_i.u_j = |sum u|^2 - sum |u_i|^2. For unit vectors this is
    the mean pairwise cosine; for vectors projected onto a subspace (norm
    <= 1) it is the projected, conservatively shrunk, cosine.
    """
    n = len(rows)
    if n < 2:
        return float("nan")
    rows64 = rows.astype(np.float64, copy=False)
    s = rows64.sum(axis=0)
    sq = float(np.einsum("ij,ij->", rows64, rows64))
    return float((s @ s - sq) / (n * (n - 1)))


def l2_normalize(x: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return (x / np.maximum(norms, eps)).astype(np.float32, copy=False)
