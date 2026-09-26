"""Network simulator: real users, organic communities and swarm operators.

Everything in this package is hidden from the detector. The detector only
ever sees :class:`mirage.network.NetworkState`.
"""

from .simulator import Simulator

__all__ = ["Simulator"]
