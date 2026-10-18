"""Toolkit-neutral cache, fingerprint and job planning for precomputed load charts."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any, Callable, NamedTuple, Optional, Sequence

from ..data.models import CraneDocument


class ChartJob(NamedTuple):
    """One (hoist, analysis mode) sweep to precompute."""

    hoist_id: str
    mode: str


class ChartKey(NamedTuple):
    """Identifies a cached sweep result; any input change yields a different key."""

    hoist_id: str
    mode: str
    outreach_step: float
    fingerprint: str


def chart_fingerprint(doc: CraneDocument, enabled_limits: dict, limit_display_names: dict) -> str:
    """Hash everything besides hoist, mode and step that a sweep result depends on."""
    digest = hashlib.sha256()
    digest.update(doc.model_dump_json().encode("utf-8"))
    for extra in (enabled_limits, limit_display_names):
        digest.update(json.dumps(extra, sort_keys=True, default=repr).encode("utf-8"))
    return digest.hexdigest()


def empty_payload() -> dict[str, Any]:
    """A mode payload with no curve, used for modes that do not apply."""
    return {"curve_data": [], "contractual_results": [], "limit_series": [], "n_points": 0}


class ChartCache:
    """A bounded least-recently-used store of mode payloads."""

    def __init__(self, max_entries: int = 48) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[ChartKey, dict[str, Any]] = OrderedDict()

    def get(self, key: ChartKey) -> Optional[dict[str, Any]]:
        payload = self._entries.get(key)
        if payload is not None:
            self._entries.move_to_end(key)
        return payload

    def put(self, key: ChartKey, payload: dict[str, Any]) -> None:
        self._entries[key] = payload
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


def plan_chart_jobs(
    visible: ChartJob, hoist_ids: Sequence[str], is_splitable: Callable[[str], bool]
) -> list[ChartJob]:
    """Order precompute jobs: the visible one, its hoist's other mode, then other hoists."""
    other_mode = "split" if visible.mode == "normal" else "normal"
    candidates = [visible, ChartJob(visible.hoist_id, other_mode)]
    for hoist_id in hoist_ids:
        if hoist_id != visible.hoist_id:
            candidates.append(ChartJob(hoist_id, "normal"))
            candidates.append(ChartJob(hoist_id, "split"))
    jobs: list[ChartJob] = []
    for job in candidates:
        if job.mode == "split" and not is_splitable(job.hoist_id):
            continue
        if job not in jobs:
            jobs.append(job)
    return jobs
