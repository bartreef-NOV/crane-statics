"""Tests for the scene frame adapter: SceneFrame values -> QML dicts."""

from unittest.mock import MagicMock

from crane_statics.qml_app.adapters.scene_adapter import SceneStateAdapter


class TestSceneStateAdapter:
    """Tests for SceneStateAdapter (pure data transformation)."""

    def test_empty_scene_frame_structure(self):
        """Verify empty frame has all required keys."""
        frame = SceneStateAdapter.empty_scene_frame()
        assert isinstance(frame, dict)
        expected_keys = {
            "revision",
            "fitRect",
            "nodes",
            "ropeSegments",
            "structuralSegments",
            "markers",
            "forceArrows",
            "moments",
            "labels",
            "guides",
            "hitTargets",
            "boomAxes",
            "winchSpools",
            "status",
        }
        assert set(frame.keys()) == expected_keys

    def test_empty_scene_frame_initial_values(self):
        """Verify empty frame has correct initial values."""
        frame = SceneStateAdapter.empty_scene_frame()
        assert frame["revision"] == 0
        assert frame["fitRect"] == {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
        assert frame["nodes"] == []
        assert frame["ropeSegments"] == []
        assert "waterline" not in frame
        assert frame["hitTargets"] == []
        assert frame["status"] is None

    def test_scene_frame_to_dict_empty_source(self):
        """Verify conversion of empty scene frame source."""
        source = MagicMock()
        source.revision = 0
        source.fit_rect = (0.0, 0.0, 100.0, 100.0)
        source.nodes = []
        source.rope_segments = []
        source.structural_segments = []
        source.markers = []
        source.force_arrows = []
        source.moments = []
        source.labels = []
        source.guides = []
        source.hit_targets = []
        source.boom_axes = []
        source.winch_spools = []
        source.status = None

        result = SceneStateAdapter.scene_frame_to_dict(source)

        assert result["revision"] == 0
        assert result["fitRect"] == {"x": 0.0, "y": 0.0, "width": 100.0, "height": 100.0}
        assert result["nodes"] == []
        assert result["ropeSegments"] == []
        assert "waterline" not in result
