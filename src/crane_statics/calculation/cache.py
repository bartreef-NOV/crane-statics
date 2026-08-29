"""Instrumented cache for directional response basis computations."""

from __future__ import annotations

import logging
from typing import Optional, Tuple, Any
from .solver.crane_solver import DirectionalResponseBasis

_LOG = logging.getLogger(__name__)


class DirectionalBasisCache:
    """Bounded cache for primitive directional response basis with instrumentation.

    Stores computed basis objects keyed by hoist, geometry, environmental magnitudes,
    and runtime configuration. Lead angles are composed from explicit lateral unit loads
    and therefore do not require distinct primitive basis entries.
    Enables cache-hit statistics for performance monitoring and prevents unbounded
    memory growth in long-running sweeps via optional max_size limit.
    """

    def __init__(self, max_size: Optional[int] = 5000):
        """Initialize cache with optional size limit.

        Args:
            max_size: Maximum number of basis objects to cache. If None, unbounded.
                      Default: 5000 (typical sweep: ~200-500 basis objects).
                      When limit reached, oldest entry is discarded (FIFO eviction).
        """
        self.max_size = max_size
        self._cache: dict[Tuple[Any, ...], DirectionalResponseBasis] = {}
        self._access_order: list[Tuple[Any, ...]] = []  # Track insertion order for FIFO eviction
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self._total_compute_time_ms = 0.0  # Track external compute time for stats

    def get(self, key: Tuple[Any, ...]) -> Optional[DirectionalResponseBasis]:
        """Retrieve basis from cache; records miss if not found."""
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        return None

    def put(self, key: Tuple[Any, ...], basis: DirectionalResponseBasis) -> None:
        """Store basis in cache; evicts oldest if max_size reached."""
        if key not in self._cache:
            # New entry: check size limit before adding
            if self.max_size is not None and len(self._cache) >= self.max_size:
                # Evict oldest (first in access order)
                oldest_key = self._access_order.pop(0)
                del self._cache[oldest_key]
                self.evictions += 1

            # Add new entry
            self._access_order.append(key)

        self._cache[key] = basis

    def clear(self) -> None:
        """Clear all cached entries and reset statistics."""
        self._cache.clear()
        self._access_order.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self._total_compute_time_ms = 0.0

    @property
    def hit_rate(self) -> float:
        """Return cache hit rate (0.0-1.0) or 0.0 if no accesses yet."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        """Return current number of cached entries."""
        return len(self._cache)

    def record_compute_time(self, duration_ms: float) -> None:
        """Record external computation time (e.g., solver run) for stats tracking."""
        self._total_compute_time_ms += float(duration_ms)

    def log_stats(self, logger: Optional[logging.Logger] = None) -> str:
        """Generate and log cache statistics.

        Returns a formatted stats string suitable for logging or display.
        """
        logger = logger or _LOG
        total = self.hits + self.misses
        hit_rate_pct = (100.0 * self.hit_rate) if total > 0 else 0.0

        stats_msg = (
            f"Cache stats: size={self.size}, hits={self.hits}, misses={self.misses}, "
            f"hit_rate={hit_rate_pct:.1f}%, evictions={self.evictions}, "
            f"max_size={self.max_size or 'unbounded'}, "
            f"external_compute_time={self._total_compute_time_ms:.1f}ms"
        )
        logger.info(stats_msg)
        return stats_msg
