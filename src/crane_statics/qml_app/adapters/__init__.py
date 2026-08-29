"""Adapters layer: pure transformations between domain and UI representations.

This layer provides view-independent transformers that convert domain objects to
QML-consumable formats. All code here is pure Python with no Qt dependencies.
"""

from .scene_adapter import SceneStateAdapter

__all__ = [
    "SceneStateAdapter",
]
