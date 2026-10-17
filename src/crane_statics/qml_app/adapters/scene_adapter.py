"""Scene frame → QML: the one place a ``SceneFrame`` becomes plain dicts.

Pure Python, no Qt. QML cannot read frozen dataclasses, so every frame crosses
into the view layer through here. The drag gesture lives in
``qml_app.scene.scene_drag``, which is its only consumer.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crane_statics.core.scene_frame import SceneFrame


class SceneStateAdapter:
    """Transforms domain/renderer state into QML-consumable display dicts.

    Pure Python; no Qt dependencies. All methods are stateless transformations.
    """

    @staticmethod
    def empty_scene_frame() -> dict[str, Any]:
        """Create an empty scene frame dict structure for QML."""
        return {
            "revision": 0,
            "fitRect": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
            "nodes": [],
            "ropeSegments": [],
            "structuralSegments": [],
            "markers": [],
            "forceArrows": [],
            "moments": [],
            "labels": [],
            "guides": [],
            "hitTargets": [],
            "boomAxes": [],
            "winchSpools": [],
            "status": None,
        }

    @staticmethod
    def scene_frame_to_dict(source: SceneFrame) -> dict[str, Any]:
        """Transform a SceneFrame domain object into a QML-compatible dict.

        Args:
            source: Domain SceneFrame object from renderer

        Returns:
            Dictionary with all fields converted to JSON-serializable types
        """
        x, y, width, height = source.fit_rect
        return {
            "revision": source.revision,
            "fitRect": {"x": x, "y": y, "width": width, "height": height},
            "nodes": [asdict(node) for node in source.nodes],
            "ropeSegments": [asdict(segment) for segment in source.rope_segments],
            "structuralSegments": [asdict(segment) for segment in source.structural_segments],
            "markers": [asdict(marker) for marker in source.markers],
            "forceArrows": [asdict(arrow) for arrow in source.force_arrows],
            "moments": [asdict(moment) for moment in source.moments],
            "labels": [asdict(label) for label in source.labels],
            "guides": [asdict(guide) for guide in source.guides],
            "hitTargets": [asdict(target) for target in source.hit_targets],
            "boomAxes": [asdict(axis) for axis in source.boom_axes],
            "winchSpools": [asdict(spool) for spool in source.winch_spools],
            "status": None if source.status is None else asdict(source.status),
        }
