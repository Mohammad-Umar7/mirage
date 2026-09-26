"""Wire format helpers.

Large numeric arrays travel as base64-encoded little-endian typed arrays
inside JSON ({"dtype": "i4", "b64": "..."}); the browser turns them into
Int32Array / Float32Array without parsing thousands of numbers.
"""

from __future__ import annotations

import base64
import json
import math

import numpy as np

DAY = 1440.0


def pack(arr, dtype: str) -> dict:
    a = np.ascontiguousarray(np.asarray(arr), dtype=np.dtype(dtype).newbyteorder("<"))
    return {"dtype": dtype, "n": int(a.size), "b64": base64.b64encode(a.tobytes()).decode("ascii")}


def clean(v):
    """Make numpy / NaN values JSON-safe."""
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 5)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def dumps(msg: dict) -> str:
    return json.dumps(clean(msg), separators=(",", ":"), ensure_ascii=False)


def clock(t: float) -> str:
    """Simulated time as 'DAY 3 · 14:05'."""
    day = int(t // DAY)
    minutes = int(t - day * DAY)
    return f"DAY {day} · {minutes // 60:02d}:{minutes % 60:02d}"
