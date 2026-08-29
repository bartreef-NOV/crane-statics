"""Demonstration of bounded cache benefits during long sweeps."""

from pathlib import Path
from crane_statics.calculation.cache import DirectionalBasisCache
from crane_statics.calculation.engine import CraneCalculator
from crane_statics.core.io import load_document


EXAMPLE = Path(__file__).parent.parent / "examples" / "crane_input_22689.json"


class TestBoundedCacheBenefits:
    """Demonstrate bounded cache utility in sweep scenarios."""

    def test_bounded_cache_prevents_memory_growth_in_sweep_simulation(self):
        """Simulate a sweep with bounded cache to show memory control."""
        # Create a bounded cache (typical sweep might have 200+ analysis points)
        bounded_cache = DirectionalBasisCache(max_size=50)
        unbounded_cache = DirectionalBasisCache(max_size=None)

        # Simulate 200 unique analysis parameter sets (boom angles × wind speeds)
        num_points = 200

        for i in range(num_points):
            # Create unique keys for each iteration
            key = (f"angle_{i}", f"wind_{i // 5}", f"accel_{i // 50}")
            basis_obj = f"DirectionalResponseBasis_{i}"

            bounded_cache.put(key, basis_obj)
            unbounded_cache.put(key, basis_obj)

        # Bounded cache stays at max_size (FIFO eviction)
        assert bounded_cache.size == 50

        # Unbounded cache grows to full 200
        assert unbounded_cache.size == 200

        # Demonstrate cache effectiveness:
        # After 200 puts, access patterns on the last 50 should hit bounded cache
        hit_count_bounded = 0
        hit_count_unbounded = 0
        initial_misses_bounded = bounded_cache.misses
        initial_misses_unbounded = unbounded_cache.misses

        # Access the last 50 items (should still be in bounded cache)
        for i in range(150, 200):
            key = (f"angle_{i}", f"wind_{i // 5}", f"accel_{i // 50}")
            if bounded_cache.get(key) is not None:
                hit_count_bounded += 1
            if unbounded_cache.get(key) is not None:
                hit_count_unbounded += 1

        # Both should have hits on the same recent entries
        assert bounded_cache.hits > initial_misses_bounded
        assert unbounded_cache.hits > initial_misses_unbounded

        # Bounded cache has limited size but still provides benefits
        print(
            f"\nBounded cache (max_size=50): {bounded_cache.hits} hits, "
            f"{bounded_cache.misses} misses"
        )
        print(f"Unbounded cache: {unbounded_cache.hits} hits, {unbounded_cache.misses} misses")

    def test_calculator_with_bounded_cache_in_sweep(self):
        """Integration: verify bounded cache works in calculator during sweep."""
        doc = load_document(EXAMPLE)
        calc = CraneCalculator(doc)

        # Typical sweep: evaluate 30 outreach points × 4 wind directions = 120 analysis points
        # But since we cache the primitive basis (which depends on boom angle, not outreach),
        # we'd expect ~30 unique basis objects for 30 boom angles

        wind_speed = 10.0

        # Simulate sweep over boom angles (0-90°) and wind directions
        num_angles = 30
        for angle_idx in range(num_angles):
            boom_angle = angle_idx * 90.0 / num_angles
            for wind_dir in ["+X", "-X", "+Y", "-Y"]:
                pt = calc.compute_analysis_point(
                    boom_angle,
                    0.0,  # outreach_m
                    "MH",
                    wind_speed_m_s=wind_speed,
                    wind_direction=wind_dir,
                )
                assert pt is not None

        # Verify cache was used effectively
        # We computed 120 points but should have only needed ~30 basis objects
        total_accesses = calc._directional_basis_cache.hits + calc._directional_basis_cache.misses
        assert total_accesses > 0

        # Hit rate should show significant reuse (with 30 angles and 4 directions,
        # we get 3 hits for every miss on average after the first miss)
        hit_rate = calc._directional_basis_cache.hit_rate
        assert hit_rate >= 0.5  # At least half of accesses should be hits

        print(f"\nCache performance in sweep: {hit_rate:.1%} hit rate")
        print(
            f"Hits: {calc._directional_basis_cache.hits}, "
            f"Misses: {calc._directional_basis_cache.misses}"
        )

    def test_opposite_offlead_angles_reuse_one_primitive_basis(self):
        doc = load_document(EXAMPLE)
        calc = CraneCalculator(doc)

        common = {
            "wind_speed_m_s": 10.0,
            "wind_direction": "+X",
            "accel_x_m_s2": 0.0,
            "accel_z_m_s2": 0.0,
            "pitch_accel_rad_s2": 0.0,
        }
        positive = calc.compute_analysis_point(45.0, 0.0, "MH", offlead_deg=5.0, **common)
        negative = calc.compute_analysis_point(45.0, 0.0, "MH", offlead_deg=-5.0, **common)

        assert positive is not None and negative is not None
        assert calc._directional_basis_cache.misses == 1
        assert calc._directional_basis_cache.hits == 1
