"""Small, dependency-free accessibility calculations used by UI validation."""

from __future__ import annotations

from collections.abc import Iterable


def _channel(value: float | int) -> float:
    normalized = float(value)
    if normalized > 1.0:
        normalized /= 255.0
    return min(1.0, max(0.0, normalized))


def relative_luminance(rgb: Iterable[float | int]) -> float:
    """Return WCAG relative luminance for an RGB triplet."""
    channels = list(rgb)
    if len(channels) != 3:
        raise ValueError("RGB values must contain exactly three channels")

    linear = []
    for channel in channels:
        value = _channel(channel)
        linear.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: Iterable[float | int], background: Iterable[float | int]) -> float:
    """Return the WCAG contrast ratio between two RGB colors."""
    foreground_luminance = relative_luminance(foreground)
    background_luminance = relative_luminance(background)
    lighter = max(foreground_luminance, background_luminance)
    darker = min(foreground_luminance, background_luminance)
    return (lighter + 0.05) / (darker + 0.05)
