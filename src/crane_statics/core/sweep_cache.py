"""Toolkit-neutral cache of load-chart probe solves and per-limit results.

A design-limit edit leaves the crane model, and so every probe solve, unchanged; and every
limit other than the edited one keeps its result. ``ComputeCache`` keeps both across
sweeps so a re-sweep only recomputes what the edit actually changed.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Any, Callable, Hashable, NamedTuple, Optional, cast

from ..data.models import CraneDocument
from .chart_envelope import ProbeSet

# (limit id, sorted (component, value) pairs): what a limit's result depends on.
LimitSignature = tuple[str, tuple[tuple[str, float], ...]]

_CONTRACTUAL = {"hoists": {"__all__": {"contractual_points", "split_contractual_points"}}}


class LimitResult(NamedTuple):
    """One limit's allowable hook load at one boom angle."""

    load_t: float
    load_kN: float
    responsive: bool


def compute_fingerprint(doc: CraneDocument) -> str:
    """Hash everything a probe solve or limit result depends on, bar the contractual points.

    The contractual points are only compared against the computed curve, never an input
    to it, so editing them must not discard cached solves.
    """
    payload = doc.model_dump_json(exclude=_CONTRACTUAL)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def limit_signature(limit_id: str, components: dict) -> LimitSignature:
    """Identify a limit by its id and component values, independent of dict order."""
    return (limit_id, tuple(sorted((str(k), float(v)) for k, v in components.items())))


def _angle_key(angle: float) -> float:
    return round(float(angle), 10)


class JobPriority:
    """Whether a sweep's probe accesses are background work; its owner may flip it any time.

    Background accesses never push out other entries: a hit does not refresh recency and
    a new entry goes in as the oldest, so it is the first to be evicted.
    """

    def __init__(self, background: bool = False) -> None:
        self.background = background


class ComputeScope:
    """A view of the cache for one (fingerprint, hoist, mode)."""

    def __init__(
        self,
        cache: "ComputeCache",
        prefix: tuple[str, str, str],
        priority: Optional[JobPriority] = None,
    ) -> None:
        self._cache = cache
        self._prefix = prefix
        self._priority = priority

    def probes(self, angle: float, build: Callable[[], Optional[ProbeSet]]) -> Optional[ProbeSet]:
        """Return the probe set at ``angle``, calling ``build`` only on a miss.

        A ``None`` result (a failed probe solve) is cached too.
        """
        key = (*self._prefix, _angle_key(angle))
        # Read on every access: the priority can change while the sweep runs.
        background = self._priority is not None and self._priority.background
        return cast(
            Optional[ProbeSet],
            self._cache._get_or_compute(self._cache._probes, key, build, background),
        )

    def limit_result(
        self, angle: float, signature: LimitSignature, compute: Callable[[], LimitResult]
    ) -> LimitResult:
        """Return the limit result at ``angle``, calling ``compute`` only on a miss."""
        key = (*self._prefix, _angle_key(angle), signature)
        return cast(LimitResult, self._cache._get_or_compute(self._cache._limits, key, compute))


class ComputeCache:
    """Bounded least-recently-used stores of probe sets and limit results."""

    def __init__(self, max_probe_sets: int = 4096, max_limit_results: int = 200000) -> None:
        self._max_probe_sets = max_probe_sets
        self._max_limit_results = max_limit_results
        self._probes: OrderedDict[Hashable, Any] = OrderedDict()
        self._limits: OrderedDict[Hashable, Any] = OrderedDict()
        self._lock = threading.Lock()

    def scope(
        self,
        fingerprint: str,
        hoist_id: str,
        mode: str,
        priority: Optional[JobPriority] = None,
    ) -> ComputeScope:
        return ComputeScope(self, (fingerprint, hoist_id, mode), priority)

    def clear(self) -> None:
        with self._lock:
            self._probes.clear()
            self._limits.clear()

    def probe_count(self) -> int:
        with self._lock:
            return len(self._probes)

    def _get_or_compute(
        self,
        store: "OrderedDict[Hashable, Any]",
        key: Hashable,
        compute: Callable[[], Any],
        background: bool = False,
    ) -> Any:
        limit = self._max_probe_sets if store is self._probes else self._max_limit_results
        with self._lock:
            if key in store:
                if not background:
                    store.move_to_end(key)
                return store[key]
        value = compute()  # outside the lock: a solve can take a while
        with self._lock:
            store[key] = value
            # A background entry goes in as the oldest: the first to go under pressure.
            store.move_to_end(key, last=not background)
            while len(store) > limit:
                store.popitem(last=False)
        return value
