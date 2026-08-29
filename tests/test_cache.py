"""Tests for DirectionalBasisCache instrumentation."""

import pytest
from pathlib import Path
from crane_statics.calculation.cache import DirectionalBasisCache
from crane_statics.calculation.engine import CraneCalculator
from crane_statics.core.io import load_document


EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


class TestDirectionalBasisCache:
    """Test cache behavior and instrumentation."""

    def test_cache_tracks_hits_and_misses(self):
        """Verify cache records hits and misses correctly."""
        cache = DirectionalBasisCache(max_size=10)

        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.hit_rate == 0.0
        assert cache.size == 0

        # First access is a miss
        key1 = ("hoist1", 45.0, 10.0)
        result = cache.get(key1)
        assert result is None
        assert cache.misses == 1
        assert cache.hits == 0
        assert cache.hit_rate == 0.0

        # Store something
        cache.put(key1, "basis_obj_1")
        assert cache.size == 1

        # Second access with same key is a hit
        result = cache.get(key1)
        assert result == "basis_obj_1"
        assert cache.hits == 1
        assert cache.misses == 1
        assert cache.hit_rate == pytest.approx(0.5)

        # New key is a miss
        key2 = ("hoist1", 45.0, 15.0)
        result = cache.get(key2)
        assert result is None
        assert cache.misses == 2
        assert cache.hit_rate == pytest.approx(1.0 / 3.0)

    def test_cache_respects_max_size_fifo(self):
        """Verify cache respects max_size with FIFO eviction."""
        cache = DirectionalBasisCache(max_size=3)

        # Add 3 items
        cache.put("key1", "obj1")
        cache.put("key2", "obj2")
        cache.put("key3", "obj3")
        assert cache.size == 3

        # Adding 4th item should evict the oldest (key1)
        cache.put("key4", "obj4")
        assert cache.size == 3

        # key1 should be gone (miss)
        assert cache.get("key1") is None
        assert cache.misses == 1

        # key2, key3, key4 should still be there
        assert cache.get("key2") == "obj2"
        assert cache.get("key3") == "obj3"
        assert cache.get("key4") == "obj4"
        assert cache.hits == 3

    def test_cache_clear_resets_statistics(self):
        """Verify clear() resets all state."""
        cache = DirectionalBasisCache(max_size=10)

        cache.put("key1", "obj1")
        _ = cache.get("key1")  # hit
        _ = cache.get("key2")  # miss

        assert cache.size == 1
        assert cache.hits == 1
        assert cache.misses == 1

        cache.clear()

        assert cache.size == 0
        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.hit_rate == 0.0

    def test_unbounded_cache_no_eviction(self):
        """Verify unbounded cache (max_size=None) never evicts."""
        cache = DirectionalBasisCache(max_size=None)

        for i in range(100):
            cache.put(f"key{i}", f"obj{i}")

        assert cache.size == 100

        # All items should still be there
        for i in range(100):
            result = cache.get(f"key{i}")
            assert result == f"obj{i}"

        assert cache.hits == 100

    def test_calculator_reuses_basis_via_instrumented_cache(self):
        """Integration test: verify CraneCalculator uses cache with hits."""
        doc = load_document(EXAMPLE)
        calc = CraneCalculator(doc)

        # Cache starts clean
        assert calc._directional_basis_cache.hits == 0
        assert calc._directional_basis_cache.misses == 0

        # First two calls with same parameters should: miss, hit

        # First call
        pt1 = calc.compute_analysis_point(
            45.0,  # boom_angle_deg
            0.0,  # outreach_m
            "MH",  # hoist_id
            wind_speed_m_s=10.0,
            wind_direction="+X",
        )
        assert pt1 is not None
        assert calc._directional_basis_cache.misses == 1
        assert calc._directional_basis_cache.hits == 0

        # Second call with identical parameters
        pt2 = calc.compute_analysis_point(
            45.0,  # boom_angle_deg (same)
            0.0,  # outreach_m (same)
            "MH",  # hoist_id (same)
            wind_speed_m_s=10.0,  # (same)
            wind_direction="+X",  # (different direction but same wind speed)
        )
        assert pt2 is not None
        # Primitive basis should be reused; second call hits the cache
        assert calc._directional_basis_cache.hits == 1
        assert calc._directional_basis_cache.misses == 1

        # Verify numerical equivalence (cache reuse doesn't change results)
        assert pt1.boom_angle_deg == pt2.boom_angle_deg
        assert pt1.outreach_m == pt2.outreach_m
        assert pt1.baseline_rope_tensions == pt2.baseline_rope_tensions
        assert pt1.sensitivity_rope_tensions == pt2.sensitivity_rope_tensions
