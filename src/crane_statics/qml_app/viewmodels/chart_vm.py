"""Load chart view model: design limits, capacity sweep and plot series."""

from __future__ import annotations

import csv
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Optional

from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot

from crane_statics.presentation.formatters import (
    ConnectionFormatter,
    HoistFormatter,
    RopeFormatter,
)
from crane_statics.core.chart_cache import (
    ChartCache,
    ChartJob,
    ChartKey,
    chart_fingerprint,
    empty_payload,
    plan_chart_jobs,
)
from crane_statics.core.document_edit import DocumentEditor, build_contractual_point
from crane_statics.core.governing_case import governing_case
from crane_statics.core.limit_auto_set import (
    ConnectionAutoSetResult,
    RopeAutoSetResult,
    compute_required_connection_capacity_kN,
    compute_required_rope_capacity_kN,
)
from crane_statics.data.models import CraneDocument
from crane_statics.qml_app.session import SessionState
from crane_statics.core.sweep import SweepCancelled, limit_series_layout, run_mode_sweep
from crane_statics.core.sweep_cache import (
    ComputeCache,
    ComputeScope,
    JobPriority,
    LimitSignature,
    compute_fingerprint,
    limit_signature,
)

from ..models.table_models import Column, RecordTableModel

if TYPE_CHECKING:
    from .scene_vm import SceneViewModel

_LOG = logging.getLogger(__name__)

LIMIT_COLUMNS = [
    Column("Limit", lambda r: r["name"]),
    Column("Unit", lambda r: r["unit"]),
    Column("Max", lambda r: r["maxValue"], decimals=1, field="maxValue", editor="number"),
    Column("On", lambda r: r["limitEnabled"], field="limitEnabled", editor="bool"),
]
CONTRACTUAL_COLUMNS = [
    Column(
        "Outreach (m)", lambda r: r["outreach"], decimals=1, field="outreach_m", editor="number"
    ),
    Column("Load (t)", lambda r: r["load"], decimals=1, field="load_t", editor="number"),
    Column("Allowable (t)", lambda r: r["allowable"]),
    Column("Status", lambda r: r["status"]),
]

_LIMIT_COLORS = [
    "#8E44AD",
    "#16A085",
    "#D35400",
    "#2980B9",
    "#C0392B",
    "#7F8C8D",
    "#27AE60",
    "#B7950B",
]


def _limit_color(position: int) -> str:
    """The colour of the limit at ``position`` in the layout of every enabled limit, so a
    limit keeps it from its first streamed point to the finished chart."""
    return _LIMIT_COLORS[position % len(_LIMIT_COLORS)]


def _contractual_row(cp: Any, allowable: str, status: str) -> dict[str, str]:
    return {
        "outreach": f"{cp.outreach_m:.1f}",
        "load": f"{cp.load_t:.1f}",
        "allowable": allowable,
        "status": status,
    }


class _SweepWorker(QThread):
    """Runs one (hoist, mode) capacity-curve sweep off the GUI thread."""

    pointsReady = pyqtSignal(object)  # list[tuple[float, float]], ascending outreach
    # (contractual point, allowable t or None, passed or None) per point, after stage 1
    contractualReady = pyqtSignal(object)
    # {limit id: [(outreach, load_t), ...]}: the limit points gained with each batch
    limitPointsReady = pyqtSignal(object)
    progress = pyqtSignal(str)
    finishedWith = pyqtSignal(object)  # the mode payload; empty_payload() if it does not apply
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        doc: CraneDocument,
        job: ChartJob,
        enabled_limits: dict,
        outreach_step: float,
        limit_display_names: dict,
        compute_scope: ComputeScope,
    ) -> None:
        # Workers stay parentless: as a child of the view model a QThread would be destroyed
        # while running when the QML engine deletes the view model.
        super().__init__()
        self._args = (
            doc,
            job.hoist_id,
            job.mode,
            enabled_limits,
            outreach_step,
            limit_display_names,
        )
        self._compute_scope = compute_scope

    def _emit_points(self, points: list) -> None:
        self.pointsReady.emit(points)
        # The sweep shares the GIL with the UI thread: let it run between batches.
        time.sleep(0)

    def _emit_contractual(self, results: list) -> None:
        self.contractualReady.emit(results)
        time.sleep(0)

    def _emit_limit_points(self, gained: dict) -> None:
        self.limitPointsReady.emit(gained)
        time.sleep(0)

    def run(self) -> None:
        try:
            payload = run_mode_sweep(
                *self._args,
                progress=self.progress.emit,
                should_cancel=self.isInterruptionRequested,
                on_points=self._emit_points,
                compute_scope=self._compute_scope,
                on_contractual=self._emit_contractual,
                on_limit_points=self._emit_limit_points,
            )
            self.finishedWith.emit(payload if payload is not None else empty_payload())
        except SweepCancelled:
            self.cancelled.emit()
        except Exception as exc:  # worker boundary: report instead of crashing the thread
            self.failed.emit(str(exc))


class _GoverningCaseWorker(QThread):
    """Re-evaluates one chart point's governing case off the GUI thread."""

    finishedWith = pyqtSignal(object)  # Optional[GoverningCase]
    failed = pyqtSignal(str)

    def __init__(
        self,
        doc: CraneDocument,
        hoist_id: str,
        mode: str,
        enabled_limits: dict,
        outreach_m: float,
        limit_id: Optional[str],
    ) -> None:
        # Parentless, as _SweepWorker: the view model holds it until `finished`.
        super().__init__()
        self._args = (doc, hoist_id, mode, enabled_limits, outreach_m, limit_id)

    def run(self) -> None:
        try:
            self.finishedWith.emit(governing_case(*self._args))
        except Exception as exc:  # worker boundary: report instead of crashing the thread
            self.failed.emit(str(exc))


class _CaseRequest(NamedTuple):
    """The governing-case evaluation in flight, with the chart its point was clicked on."""

    worker: _GoverningCaseWorker
    generation: int
    key: ChartKey
    outreach_m: float
    # The status shown before the request, put back when it ends.
    previous_status: str


def _is_sweep_status(text: str) -> bool:
    """Whether ``text`` is a status the sweep itself wrote (progress, done or error)."""
    return text == "" or text.startswith(("Sweeping", "Stage ", "Done - ", "⚠ Sweep error"))


class _JobStream:
    """What the sweep in flight has delivered so far; shown while it is the wanted chart.

    Every job starts with a fresh one, so nothing of an earlier job can reach the chart.
    """

    def __init__(
        self,
        layout: list[tuple[str, str, int]],
        kept: Optional[dict[str, list[list[float]]]] = None,
    ) -> None:
        # (limit id, label, rank) of every enabled limit, in display order.
        self.layout = layout
        self.points: list[list[float]] = []
        # Limits the chart on screen already shows unchanged: their points stay put and the
        # sweep's replay of them is ignored.
        self.kept = kept if kept is not None else {}
        self.limit_points: dict[str, list[list[float]]] = dict(self.kept)
        # The stage-1 verdicts; None until they arrive.
        self.verdicts: Optional[list] = None

    def limit_series(self) -> list[dict[str, Any]]:
        """One series per limit that has points, coloured by its place in the layout.

        The point lists are the stream's own, not copies: copying them on every batch cost
        seconds over a fine sweep, and the view only reads them when ``chartUpdated`` fires."""
        return [
            {
                "id": limit_id,
                "label": label,
                "color": _limit_color(position),
                "points": self.limit_points[limit_id],
            }
            for position, (limit_id, label, _rank) in enumerate(self.layout)
            if self.limit_points.get(limit_id)
        ]


class _DisplayedChart(NamedTuple):
    """What a finished chart on screen was computed from, to keep its unchanged limit series."""

    key: ChartKey
    compute: str
    signatures: dict[str, LimitSignature]


class _RunningJob(NamedTuple):
    """The one sweep in flight, with the key and generation it started under."""

    job: ChartJob
    key: ChartKey
    generation: int
    worker: _SweepWorker
    # Its probe-cache priority; flipped to visible here when it becomes the wanted chart.
    priority: JobPriority
    stream: _JobStream


class ChartViewModel(QObject):
    """Owns design limits, the sweep lifecycle and the rendered chart series."""

    hoistsChanged = pyqtSignal()
    chartModeChanged = pyqtSignal()
    statusChanged = pyqtSignal()
    limitsChanged = pyqtSignal()
    chartUpdated = pyqtSignal()
    chartCompleteChanged = pyqtSignal()
    contractualChanged = pyqtSignal()
    preferencesChanged = pyqtSignal()
    resetViewRequested = pyqtSignal()
    # A governing case was applied to the Scene: QML switches to the Scene tab.
    showSceneRequested = pyqtSignal()

    def __init__(self, session: SessionState, parent=None):
        super().__init__(parent)
        self._session = session
        self._model = session.model
        self._status_text = ""
        self._stale = False
        self._busy = False
        self._shutting_down = False
        self._outreach_step = 1.0
        self._cache = ChartCache()
        # Probe solves and per-limit results beneath the chart cache: a limit edit re-sweeps
        # without solving again. Replaced, never cleared, when the document changes.
        self._compute_cache = ComputeCache()
        # The compute fingerprint the cache holds entries for; None while it is empty.
        self._compute_cache_fingerprint: Optional[str] = None
        self._generation = 0
        self._fingerprint_generation = -1
        self._fingerprint = ""
        # Jobs waiting to run, the one in flight and every thread not yet exited (a
        # QThread must outlive its run(), so workers are held until `finished`).
        self._queue: list[ChartJob] = []
        self._running: Optional[_RunningJob] = None
        self._threads: set[QThread] = set()
        # The Scene a governing case is shown in, and the one evaluation in flight.
        self._scene_vm: Optional[SceneViewModel] = None
        self._case_request: Optional[_CaseRequest] = None
        self._partial = False
        self._displayed_key: Optional[ChartKey] = None
        self._displayed_chart: Optional[_DisplayedChart] = None

        self._curve_points: list[list[float]] = []
        self._limit_series: list[dict[str, Any]] = []
        self._markers: list[dict[str, Any]] = []
        # Streamed batches coalesce into one chartUpdated per event-loop turn.
        self._chart_update_pending = False
        self._limit_series_dirty = False

        self._rope_limits_model = RecordTableModel(
            LIMIT_COLUMNS, self, commit=self._commit_limit_edit("rope")
        )
        self._connection_limits_model = RecordTableModel(
            LIMIT_COLUMNS, self, commit=self._commit_limit_edit("connection")
        )
        self._contractual_model = RecordTableModel(
            CONTRACTUAL_COLUMNS, self, commit=self._commit_contractual_edit
        )

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(250)
        self._refresh_timer.timeout.connect(self.draw)

        self._session.document_changed.connect(self._on_document_changed)
        self._session.content_changed.connect(self._on_content_changed)
        self._session.hoist_selected.connect(lambda _hoist_id: self.reload())

    # ------------------------------------------------------------------
    # Selection and mode
    # ------------------------------------------------------------------

    @pyqtProperty(list, notify=hoistsChanged)
    def hoistIds(self) -> list:
        return self._model.payload_hoist_ids()

    @pyqtProperty(str, notify=hoistsChanged)
    def selectedHoistId(self) -> str:
        return self._model.selected_hoist_id or ""

    @pyqtSlot(str)
    def selectHoist(self, hoist_id: str) -> None:
        if not hoist_id or hoist_id == self._model.selected_hoist_id:
            return
        self._model.select_payload_hoist(hoist_id)

    @pyqtProperty(bool, notify=chartModeChanged)
    def splitable(self) -> bool:
        return self._model.is_splitable_hoist(self._model.selected_hoist_id)

    @pyqtProperty(str, notify=chartModeChanged)
    def chartMode(self) -> str:
        return self._current_chart_mode()

    def _current_chart_mode(self) -> str:
        return self._model.chart_mode_for_hoist(self._model.selected_hoist_id)

    @pyqtSlot(str)
    def setChartMode(self, mode: str) -> None:
        previous = self._current_chart_mode()
        normalized = self._model.set_chart_mode(self._model.selected_hoist_id, mode)
        if normalized == previous:
            return
        self.chartModeChanged.emit()
        self._rebuild_contractual_model()
        self._show_or_prioritize()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @pyqtProperty(str, notify=statusChanged)
    def statusText(self) -> str:
        return self._status_text

    @pyqtProperty(bool, notify=statusChanged)
    def stale(self) -> bool:
        return self._stale

    @pyqtProperty(bool, notify=statusChanged)
    def busy(self) -> bool:
        return self._busy

    def _set_status(self, text: str) -> None:
        self._status_text = text
        self.statusChanged.emit()

    def _set_stale(self, stale: bool) -> None:
        self._stale = bool(stale)
        self.statusChanged.emit()
        if not self._shutting_down and self._stale and self._model.document is not None:
            self._refresh_timer.start()

    @pyqtProperty(float, notify=statusChanged)
    def outreachStep(self) -> float:
        return self._outreach_step

    @pyqtSlot(float)
    def setOutreachStep(self, value: float) -> None:
        self._outreach_step = max(0.01, float(value))
        self.statusChanged.emit()
        self._set_stale(True)

    # ------------------------------------------------------------------
    # Design limits
    # ------------------------------------------------------------------

    @pyqtProperty(QObject, constant=True)
    def ropeLimitsModel(self) -> QObject:
        return self._rope_limits_model

    @pyqtProperty(QObject, constant=True)
    def connectionLimitsModel(self) -> QObject:
        return self._connection_limits_model

    def _limit_rows(self, kind: str) -> list[dict[str, Any]]:
        doc = self._model.document
        rows: list[dict[str, Any]] = []
        for dl in self._model.design_limits:
            if dl.kind != kind:
                continue
            if kind == "rope":
                name = HoistFormatter.display_name_for_limit_id(dl.id, doc)
                unit = RopeFormatter.component_unit(dl.component)
            else:
                name = ConnectionFormatter.format_label(dl.entity_id, dl.component)
                unit = ConnectionFormatter.component_unit(dl.component)
            rows.append(
                {
                    "limitId": dl.id,
                    "name": name,
                    "unit": unit,
                    "maxValue": "" if dl.max_kN is None else f"{float(dl.max_kN):.1f}",
                    "limitEnabled": bool(dl.enabled),
                    "tooltip": "",
                }
            )
        return rows

    def _refresh_limits_models(self) -> None:
        self._rope_limits_model.set_records(self._limit_rows("rope"))
        self._connection_limits_model.set_records(self._limit_rows("connection"))
        self.limitsChanged.emit()

    def _commit_limit_edit(self, kind: str):
        def commit(row: int, field: str, value: Any) -> bool:
            model = self._rope_limits_model if kind == "rope" else self._connection_limits_model
            record = model.record_at(row)
            if record is None:
                return False
            if field == "limitEnabled":
                self.setLimitEnabled(record["limitId"], bool(value))
            else:
                self.setLimitMax(record["limitId"], str(value))
            return True

        return commit

    def _commit_contractual_edit(self, row: int, field: str, value: Any) -> bool:
        points = self._contractual_points()
        if not (0 <= row < len(points)):
            return False
        try:
            fields = {
                "outreach_m": float(points[row].outreach_m),
                "load_t": float(points[row].load_t),
            }
            fields[field] = float(value)
        except (TypeError, ValueError):
            return False
        self.updateContractualPoint(row, fields)
        return True

    def _limit_by_id(self, limit_id: str):
        return self._model.design_limits_by_id.get(limit_id)

    @pyqtSlot(str, str)
    def setLimitMax(self, limit_id: str, value: str) -> None:
        dl = self._limit_by_id(limit_id)
        if dl is None:
            return
        text = str(value).strip()
        try:
            dl.max_kN = float(text) if text else None
        except ValueError:
            return
        self._model.mark_content_changed()
        self._refresh_limits_models()
        self._set_stale(True)

    @pyqtSlot(str, bool)
    def setLimitEnabled(self, limit_id: str, enabled: bool) -> None:
        dl = self._limit_by_id(limit_id)
        if dl is None:
            return
        dl.enabled = bool(enabled)
        self._model.mark_content_changed()
        self._refresh_limits_models()
        self._set_stale(True)

    @pyqtSlot(str)
    def autoSetLimit(self, limit_id: str) -> None:
        doc = self._model.document
        dl = self._limit_by_id(limit_id)
        if doc is None or dl is None:
            self._set_status("Could not compute: no document loaded")
            return

        auto: RopeAutoSetResult | ConnectionAutoSetResult
        if dl.kind == "rope":
            rope_id = limit_id[:-2] if limit_id.endswith("_T") else limit_id
            auto = compute_required_rope_capacity_kN(doc, rope_id)
            unit = RopeFormatter.component_unit(dl.component)
        else:
            auto = compute_required_connection_capacity_kN(doc, dl.entity_id, dl.component)
            unit = ConnectionFormatter.component_unit(dl.component)

        if auto.required_kN is None:
            self._set_status(f"Could not compute: {auto.message}")
            return

        if dl.component == "min_bearing_line_load" and auto.required_kN <= 0.0:
            self._set_status(f"No uplift in any contractual case: {dl.id} left unchanged")
            return

        dl.max_kN = float(auto.required_kN)
        dl.enabled = True
        self._model.mark_content_changed()
        self._set_status(f"Auto-set {dl.id} to {auto.required_kN:.1f} {unit}")
        self._refresh_limits_models()
        self._set_stale(True)

    @pyqtSlot(str, int)
    def autoSetLimitRow(self, kind: str, row: int) -> None:
        """Auto-set the limit shown at ``row`` of the rope or connection limits table."""
        model = self._rope_limits_model if kind == "rope" else self._connection_limits_model
        record = model.record_at(row)
        if record is not None:
            self.autoSetLimit(record["limitId"])

    def _enabled_limits(self) -> dict:
        return {
            dl.id: {dl.component: dl.max_kN}
            for dl in self._model.design_limits
            if dl.enabled and dl.max_kN is not None
        }

    def _limit_display_names(self) -> dict:
        doc = self._model.document
        names = {}
        for dl in self._model.design_limits:
            if dl.kind == "rope":
                names[dl.id] = HoistFormatter.display_name_for_limit_id(dl.id, doc)
            else:
                names[dl.id] = ConnectionFormatter.format_label(dl.entity_id, dl.component)
        return names

    # ------------------------------------------------------------------
    # Contractual points
    # ------------------------------------------------------------------

    @pyqtProperty(QObject, constant=True)
    def contractualModel(self) -> QObject:
        return self._contractual_model

    @pyqtSlot(int, result="QVariantMap")
    def contractualFields(self, row: int) -> dict:
        points = self._contractual_points()
        if not (0 <= row < len(points)):
            return {}
        return {"outreach_m": float(points[row].outreach_m), "load_t": float(points[row].load_t)}

    @pyqtSlot(QUrl, result=str)
    def toLocalPath(self, url: QUrl) -> str:
        return str(url.toLocalFile() if url.isLocalFile() else url.toString())

    def _contractual_points(self) -> list:
        return list(
            self._model.contractual_points_for_mode(
                self._model.selected_hoist_id,
                self._current_chart_mode(),
            )
        )

    def _rebuild_contractual_model(self) -> None:
        rows = [_contractual_row(cp, "", "pending") for cp in self._contractual_points()]
        self._contractual_model.set_records(rows)
        self.contractualChanged.emit()

    @pyqtSlot("QVariantMap")
    def addContractualPoint(self, fields: dict) -> None:
        self._edit_contractual(
            lambda editor, hoist_id: editor.add_contractual_point(
                hoist_id,
                build_contractual_point(fields.get("outreach_m", 0.0), fields.get("load_t", 0.0)),
                self._current_chart_mode(),
            )
        )

    @pyqtSlot(int, "QVariantMap")
    def updateContractualPoint(self, row: int, fields: dict) -> None:
        self._edit_contractual(
            lambda editor, hoist_id: editor.update_contractual_point(
                hoist_id,
                row,
                build_contractual_point(fields.get("outreach_m", 0.0), fields.get("load_t", 0.0)),
                self._current_chart_mode(),
            )
        )

    @pyqtSlot(int)
    def deleteContractualPoint(self, row: int) -> None:
        self._edit_contractual(
            lambda editor, hoist_id: editor.delete_contractual_point(
                hoist_id, row, self._current_chart_mode()
            )
        )

    def _edit_contractual(self, mutate) -> None:
        doc = self._model.document
        if doc is None or not self._model.selected_hoist_id:
            return
        try:
            mutate(DocumentEditor(doc), self._model.selected_hoist_id)
        except ValueError as exc:
            self._set_status(str(exc))
            return
        self._model.mark_content_changed()
        self._rebuild_contractual_model()
        self._set_stale(True)

    @pyqtSlot()
    def resetView(self) -> None:
        self.resetViewRequested.emit()

    @pyqtSlot()
    def shutdown(self) -> None:
        """Stop timer and worker activity before the application event loop exits."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self._refresh_timer.stop()
        self._queue.clear()
        self._running = None
        self._case_request = None
        threads = list(self._threads)
        for worker in threads:
            worker.requestInterruption()
        for worker in threads:
            worker.wait()
        self._threads.clear()

    # ------------------------------------------------------------------
    # Sweep
    # ------------------------------------------------------------------

    def _wanted_job(self) -> Optional[ChartJob]:
        if self._model.document is None or not self._model.selected_hoist_id:
            return None
        return ChartJob(self._model.selected_hoist_id, self._current_chart_mode())

    def _job_key(self, job: ChartJob) -> ChartKey:
        """A job's cache key under the current inputs; the fingerprint is kept per generation."""
        doc = self._model.document
        if doc is not None and self._fingerprint_generation != self._generation:
            self._fingerprint = chart_fingerprint(
                doc, self._enabled_limits(), self._limit_display_names()
            )
            self._fingerprint_generation = self._generation
        return ChartKey(job.hoist_id, job.mode, self._outreach_step, self._fingerprint)

    def _wanted_key(self) -> Optional[ChartKey]:
        """The cache key of the chart that should be on screen right now."""
        job = self._wanted_job()
        return None if job is None else self._job_key(job)

    @pyqtSlot()
    def draw(self) -> None:
        """Show the wanted chart, then queue every uncomputed chart behind it."""
        if self._shutting_down:
            return
        self._refresh_timer.stop()
        visible = self._wanted_job()
        key = self._wanted_key()
        if visible is None or key is None:
            self._set_status("No document loaded")
            return
        if self._cache.get(key) is not None:
            self._show_wanted(force=False)
        planned = plan_chart_jobs(visible, self.hoistIds, self._model.is_splitable_hoist)
        self._queue = [job for job in planned if self._cache.get(self._job_key(job)) is None]
        running = self._running
        if running is not None and not running.worker.isInterruptionRequested():
            if running.generation != self._generation or running.key != self._job_key(running.job):
                running.worker.requestInterruption()
            elif running.job in self._queue:
                self._queue.remove(running.job)
                if running.job == visible:
                    running.priority.background = False
        if self._queue and self._queue[0] == visible:
            self._prioritize(visible)
        else:
            self._pump()
        self._update_busy()

    def _show_or_prioritize(self) -> None:
        """Show the wanted chart; if it is not computed yet, move it to the front of the queue."""
        self._show_wanted()
        job = self._wanted_job()
        key = self._wanted_key()
        idle = self._running is None and not self._queue
        # When idle, the stale timer started by _show_wanted plans the work instead.
        if job is not None and key is not None and self._cache.get(key) is None and not idle:
            self._prioritize(job)
        self._update_busy()

    def _prioritize(self, job: ChartJob) -> None:
        """Run ``job`` next: a different job in flight is cancelled and requeued behind it."""
        running = self._running
        if (
            running is not None
            and running.job == job
            and running.generation == self._generation
            and running.key == self._job_key(job)
            and not running.worker.isInterruptionRequested()
        ):
            running.priority.background = False
            return
        if job in self._queue:
            self._queue.remove(job)
        self._queue.insert(0, job)
        if running is not None and not running.worker.isInterruptionRequested():
            # Its partial work is lost; the cancel lands in _on_worker_cancelled.
            running.worker.requestInterruption()
            if (
                running.job != job
                and running.generation == self._generation
                and running.job not in self._queue
            ):
                self._queue.insert(1, running.job)
        self._pump()

    def _pump(self) -> None:
        """Start the next queued chart that is not cached, unless a sweep is in flight."""
        if self._shutting_down or self._running is not None:
            return
        while self._queue:
            job = self._queue.pop(0)
            if self._cache.get(self._job_key(job)) is None and self._start(job):
                return

    def _start(self, job: ChartJob) -> bool:
        doc = self._model.document
        if doc is None or job.hoist_id not in self.hoistIds:
            return False
        # The worker owns a private copy; its key is fingerprinted from that copy.
        doc_copy = doc.model_copy(deep=True)
        limits = self._enabled_limits()
        names = self._limit_display_names()
        self._fingerprint = chart_fingerprint(doc_copy, limits, names)
        self._fingerprint_generation = self._generation
        key = ChartKey(job.hoist_id, job.mode, self._outreach_step, self._fingerprint)
        if self._cache.get(key) is not None:
            return False

        compute = compute_fingerprint(doc_copy)
        if self._compute_cache_fingerprint not in (None, compute):
            # Entries of another document state can never hit: start afresh. No worker is
            # running here, and a finishing one keeps its own reference to the old cache.
            self._compute_cache = ComputeCache()
        self._compute_cache_fingerprint = compute
        # Background jobs must not evict the wanted chart's probe solves.
        priority = JobPriority(background=key != self._wanted_key())
        # One scope per (hoist, mode): the hook mass, and so every result, differs per mode.
        scope = self._compute_cache.scope(compute, job.hoist_id, job.mode, priority)
        worker = _SweepWorker(doc_copy, job, limits, self._outreach_step, names, scope)
        worker.pointsReady.connect(lambda points, w=worker: self._on_worker_points(w, points))
        worker.contractualReady.connect(
            lambda results, w=worker: self._on_worker_contractual(w, results)
        )
        worker.limitPointsReady.connect(
            lambda gained, w=worker: self._on_worker_limit_points(w, gained)
        )
        worker.progress.connect(lambda text, w=worker: self._on_worker_progress(w, text))
        worker.finishedWith.connect(lambda payload, w=worker: self._on_worker_finished(w, payload))
        worker.failed.connect(lambda message, w=worker: self._on_worker_failed(w, message))
        worker.cancelled.connect(lambda w=worker: self._on_worker_cancelled(w))
        worker.finished.connect(lambda w=worker: self._threads.discard(w))
        worker.finished.connect(worker.deleteLater)
        kept = {} if priority.background else self._unchanged_limit_series(key, compute, limits)
        stream = _JobStream(limit_series_layout(doc_copy, limits, names), kept)
        self._running = _RunningJob(job, key, self._generation, worker, priority, stream)
        self._threads.add(worker)
        if not priority.background:
            self._show_stream()
        worker.start()
        return True

    def _unchanged_limit_series(
        self, key: ChartKey, compute: str, limits: dict
    ) -> dict[str, list[list[float]]]:
        """Points of the limit series on screen that a sweep for ``key`` would reproduce.

        After a limit edit only the changed or added limits differ; the rest of the finished
        chart on screen (same hoist, mode, step and inputs) stays instead of being redrawn."""
        shown = self._displayed_chart
        if (
            shown is None
            or self._partial
            or shown.key != self._displayed_key
            or (shown.key.hoist_id, shown.key.mode, shown.key.outreach_step)
            != (key.hoist_id, key.mode, key.outreach_step)
            or shown.compute != compute
        ):
            return {}
        same = {
            lid
            for lid, comps in limits.items()
            if shown.signatures.get(lid) == self._signature(lid, comps)
        }
        return {s["id"]: s["points"] for s in self._limit_series if s["id"] in same}

    @staticmethod
    def _signature(limit_id: str, components: dict) -> LimitSignature:
        return limit_signature(limit_id, {c: v or 0.0 for c, v in components.items()})

    def _remember_displayed(self, key: ChartKey) -> None:
        doc = self._model.document
        if doc is None:
            self._displayed_chart = None
            return
        self._displayed_chart = _DisplayedChart(
            key,
            compute_fingerprint(doc),
            {lid: self._signature(lid, comps) for lid, comps in self._enabled_limits().items()},
        )

    def _running_is_wanted(self) -> bool:
        """Whether the sweep in flight is computing the chart that should be on screen."""
        running = self._running
        return (
            running is not None
            and running.generation == self._generation
            and not running.worker.isInterruptionRequested()
            and running.key == self._wanted_key()
        )

    def _update_busy(self) -> None:
        """`busy` is true while the wanted chart is queued or computing, not for background jobs."""
        job = self._wanted_job()
        key = self._wanted_key()
        pending = job is not None and (job in self._queue or self._running_is_wanted())
        self._busy = bool(pending and key is not None and self._cache.get(key) is None)
        self.statusChanged.emit()

    def _cancel_all(self) -> None:
        """Drop the queue and cancel the sweep in flight; its result will be discarded."""
        self._queue.clear()
        if self._running is not None:
            self._running.worker.requestInterruption()

    @pyqtSlot()
    def drawBlocking(self) -> None:
        """Synchronous sweep of the wanted chart, used by tests and headless runs."""
        doc = self._model.document
        key = self._wanted_key()
        if doc is None or key is None:
            return
        if self._cache.get(key) is None:
            payload = run_mode_sweep(
                doc,
                key.hoist_id,
                key.mode,
                self._enabled_limits(),
                self._outreach_step,
                self._limit_display_names(),
            )
            self._cache.put(key, payload or empty_payload())
        self._show_wanted()

    # Worker signals arrive queued on the GUI thread. Only the job in flight is listened
    # to; anything from a worker that is no longer running (or after shutdown) is dropped.

    def _stopped(self) -> bool:
        """True after shutdown(), or once a parent deleted this object without calling it."""
        if not self._shutting_down and sip.isdeleted(self):
            # The QML engine tore this object down: wind the workers down, render nothing.
            self._shutting_down = True
            self._queue.clear()
            for worker in self._threads:
                worker.requestInterruption()
        return self._shutting_down

    def _take_running(self, worker: _SweepWorker) -> Optional[_RunningJob]:
        running = self._running
        if self._stopped() or running is None or running.worker is not worker:
            return None
        self._running = None
        return running

    def _on_worker_points(self, worker: _SweepWorker, points: list) -> None:
        running = self._running
        if self._stopped() or running is None or running.worker is not worker:
            return
        batch = [[float(x), float(y)] for x, y in points]
        running.stream.points.extend(batch)
        if self._partial and self._running_is_wanted():
            self._curve_points.extend(batch)
            self._schedule_chart_update()

    def _on_worker_contractual(self, worker: _SweepWorker, results: list) -> None:
        running = self._running
        if self._stopped() or running is None or running.worker is not worker:
            return
        running.stream.verdicts = list(results)
        if self._partial and self._running_is_wanted():
            self._show_contractual(running.stream.verdicts)
            self._schedule_chart_update()

    def _on_worker_limit_points(self, worker: _SweepWorker, gained: dict) -> None:
        running = self._running
        if self._stopped() or running is None or running.worker is not worker:
            return
        for limit_id, points in gained.items():
            if limit_id in running.stream.kept:
                continue
            running.stream.limit_points.setdefault(str(limit_id), []).extend(
                [float(x), float(y)] for x, y in points
            )
        if self._partial and self._running_is_wanted():
            self._limit_series_dirty = True
            self._schedule_chart_update()

    def _schedule_chart_update(self) -> None:
        """Emit chartUpdated once after the streamed batches delivered in this loop turn."""
        if not self._chart_update_pending:
            self._chart_update_pending = True
            QTimer.singleShot(0, self._flush_chart_update)

    def _flush_chart_update(self) -> None:
        if not self._chart_update_pending:
            return  # a direct emit already showed everything
        self._chart_update_pending = False
        running = self._running
        if self._stopped() or running is None or not (self._partial and self._running_is_wanted()):
            self._limit_series_dirty = False
            return
        if self._limit_series_dirty:
            self._limit_series_dirty = False
            self._limit_series = running.stream.limit_series()
        self.chartUpdated.emit()

    def _on_worker_progress(self, worker: _SweepWorker, text: str) -> None:
        running = self._running
        if self._stopped() or running is None or running.worker is not worker:
            return
        if self._running_is_wanted():
            self._set_status(text)

    def _on_worker_finished(self, worker: _SweepWorker, payload: dict) -> None:
        running = self._take_running(worker)
        if running is not None:
            self._on_sweep_finished(running.key, payload, running.generation)

    def _on_worker_failed(self, worker: _SweepWorker, message: str) -> None:
        running = self._take_running(worker)
        if running is not None:
            self._on_sweep_failed(message, running.key, running.generation)

    def _on_worker_cancelled(self, worker: _SweepWorker) -> None:
        running = self._take_running(worker)
        if running is not None:
            self._after_job(running.key)

    def _on_sweep_finished(
        self, key: ChartKey, payload: Optional[dict], generation: Optional[int] = None
    ) -> None:
        # Store under the key the sweep started with, unless an edit happened since; it is
        # shown only if it is still the wanted chart.
        if generation is None or generation == self._generation:
            self._cache.put(key, payload or empty_payload())
        self._after_job(key)

    def _on_sweep_failed(
        self, message: str, key: ChartKey, generation: Optional[int] = None
    ) -> None:
        # A failed background job marks nothing stale; it is retried on the next draw().
        _LOG.warning("Chart sweep failed for %s/%s: %s", key.hoist_id, key.mode, message)
        if key == self._wanted_key() and (generation is None or generation == self._generation):
            self._set_status("⚠ Sweep error")
        self._after_job(key)

    def _after_job(self, key: ChartKey) -> None:
        """Show the wanted chart if it is now cached, then start the next job."""
        wanted = self._wanted_key()
        if wanted is not None and self._cache.get(wanted) is not None:
            # Re-render only the chart this job completed; a background result leaves
            # the display alone and restores only a sweep status.
            self._show_wanted(force=wanted == key)
        self._pump()
        if self._partial and not self._running_is_wanted():
            # The wanted sweep failed, was cancelled or discarded: never leave its partial
            # curve on screen as if it were a finished chart.
            self._clear_display()
        # Always emits statusChanged so QML's `busy` follows.
        self._update_busy()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _show_wanted(self, force: bool = True) -> None:
        """Render the wanted chart if cached, or its partial curve while it is computing;
        otherwise clear the display and mark it stale. Without ``force`` a chart already
        on screen is not rendered again."""
        key = self._wanted_key()
        payload = self._cache.get(key) if key is not None else None
        if payload is None:
            if self._running_is_wanted():
                self._show_stream()
                return
            self._clear_display()
            self._set_stale(self._model.document is not None)
            return
        rendered = force or key != self._displayed_key
        if rendered:
            self._render_payload(payload)
            self._set_partial(False)
            self._displayed_key = key
            if key is not None:
                self._remember_displayed(key)
        self._set_stale(False)
        # A chart already on screen keeps an unrelated message such as "Exported ...".
        if rendered or _is_sweep_status(self._status_text):
            self._set_status(f"Done - {payload.get('n_points', 0)} points")

    def _show_stream(self) -> None:
        """Display what the wanted chart's sweep has delivered so far: the capacity curve,
        the limit series with points and the contractual points, pending until stage 1
        has decided them."""
        running = self._running
        stream = running.stream if running is not None else _JobStream([])
        self._curve_points = [list(point) for point in stream.points]
        self._limit_series = stream.limit_series()
        if stream.verdicts is None:
            pending = [(cp, None, None) for cp in self._contractual_points()]
            self._show_contractual(pending, undecided="")
        else:
            self._show_contractual(stream.verdicts)
        self._set_partial(True)
        self._displayed_key = None
        self._emit_chart_updated()
        self._set_stale(False)
        self._set_status("Sweeping...")

    def _clear_display(self) -> None:
        self._curve_points = []
        self._limit_series = []
        self._markers = []
        # Drop the allowables a streamed or rendered chart left in the table.
        self._rebuild_contractual_model()
        self._set_partial(False)
        self._displayed_key = None
        self._emit_chart_updated()

    def _emit_chart_updated(self) -> None:
        """Emit now; the display is complete, so a queued streamed update is redundant."""
        self._chart_update_pending = False
        self._limit_series_dirty = False
        self.chartUpdated.emit()

    def _set_partial(self, partial: bool) -> None:
        if partial != self._partial:
            self._partial = partial
            self.chartCompleteChanged.emit()

    @pyqtProperty(bool, notify=chartCompleteChanged)
    def chartComplete(self) -> bool:
        """False while the displayed curve is a partial stream, not a finished payload."""
        return not self._partial

    def _show_contractual(self, results: list, undecided: str = "-") -> None:
        """Markers and table rows from (contractual point, allowable t or None, passed or
        None) tuples; ``undecided`` is the allowable shown where there is none."""
        self._markers = []
        contractual_rows = []
        for cp, allowable, passed in results:
            status = "pending" if passed is None else ("pass" if passed else "fail")
            # The preference hides plot markers only; the table still lists every point.
            self._markers.append(
                {"outreach": float(cp.outreach_m), "load": float(cp.load_t), "status": status}
            )
            text = undecided if allowable is None else f"{float(allowable):.1f}"
            contractual_rows.append(_contractual_row(cp, text, status))
        if contractual_rows:
            self._contractual_model.set_records(contractual_rows)
            self.contractualChanged.emit()

    def _limit_positions(self) -> dict[str, int]:
        """Each enabled limit's place in the display order of all enabled limits."""
        doc = self._model.document
        hoist_id = self._model.selected_hoist_id
        if doc is None or not hoist_id:
            return {}
        layout = limit_series_layout(doc, self._enabled_limits(), self._limit_display_names())
        return {limit_id: position for position, (limit_id, _label, _rank) in enumerate(layout)}

    def _render_payload(self, payload: dict[str, Any]) -> None:
        self._curve_points = [[float(x), float(y)] for x, y in payload.get("curve_data", [])]
        # The payload is the wanted chart's, computed with the limits enabled now.
        positions = self._limit_positions()
        self._limit_series = [
            {
                "id": str(limit_id),
                "label": str(label),
                "color": _limit_color(positions.get(str(limit_id), index)),
                "points": [[float(x), float(y)] for x, y in points],
            }
            for index, (limit_id, label, _rank, points) in enumerate(
                payload.get("limit_series", [])
            )
        ]
        self._show_contractual(payload.get("contractual_results", []))
        self._emit_chart_updated()

    @pyqtProperty("QVariantList", notify=chartUpdated)
    def curvePoints(self) -> list:
        return self._curve_points

    @pyqtProperty("QVariantList", notify=chartUpdated)
    def limitSeries(self) -> list:
        return self._limit_series

    @pyqtProperty("QVariantList", notify=chartUpdated)
    def markers(self) -> list:
        return self._markers

    @pyqtProperty("QVariantMap", notify=chartUpdated)
    def axisRanges(self) -> dict:
        hoist = self._model.payload_hoist_by_id(self._model.selected_hoist_id)
        if self._partial and hoist is not None:
            # A chart still being computed: x spans the hoist's outreach limits and y starts
            # at 0, so the axes do not jump as batches arrive.
            lo = float(hoist.outreach_min_m or 0.0)
            hi = float(hoist.outreach_max_m or 200.0)
            lo, hi = min(lo, hi), max(lo, hi)
            # Until the first curve batch the contractual markers set y, so they show;
            # limit series never stretch it.
            y_values = [p[1] for p in self._curve_points] or [m["load"] for m in self._markers]
            y_top = max(y_values, default=1.0)
            x_pad = max(1.0, (hi - lo) * 0.05)
            return {
                "xMin": lo - x_pad,
                "xMax": hi + x_pad,
                "yMin": 0.0,
                "yMax": y_top + max(1.0, y_top * 0.05),
            }
        xs = [p[0] for p in self._curve_points] + [m["outreach"] for m in self._markers]
        ys = [p[1] for p in self._curve_points]
        fallback_ys = [m["load"] for m in self._markers]
        for series in self._limit_series:
            xs.extend(p[0] for p in series["points"])
            fallback_ys.extend(p[1] for p in series["points"])
        if not ys:
            ys = fallback_ys
        if not xs or not ys:
            return {"xMin": 0.0, "xMax": 1.0, "yMin": 0.0, "yMax": 1.0}
        x_pad = max(1.0, (max(xs) - min(xs)) * 0.05)
        y_pad = max(1.0, (max(ys) - min(ys)) * 0.05)
        return {
            "xMin": min(xs) - x_pad,
            "xMax": max(xs) + x_pad,
            "yMin": max(0.0, min(ys) - y_pad),
            "yMax": max(ys) + y_pad,
        }

    # ------------------------------------------------------------------
    # Governing case
    # ------------------------------------------------------------------

    def set_scene_view_model(self, scene_vm: SceneViewModel) -> None:
        """The Scene a clicked chart point's governing case is applied to."""
        self._scene_vm = scene_vm

    def _governing_case_chart(self, series_id: str) -> Optional[ChartKey]:
        """The key of the finished chart on screen, if ``series_id`` (a limit id, or "" for
        the combined curve) is one of its curves and a governing case can be asked for.

        Decided from the chart state alone. The slot has no notify signal, so QML asks
        it once per opening, in the menu's onAboutToShow."""
        key = self._displayed_key
        if (
            self._scene_vm is None
            or self._model.document is None
            or self._stale
            or self._busy
            or self._partial
            or self._case_request is not None
            or key is None
            or key.hoist_id != self._model.selected_hoist_id
            or key.mode != self._current_chart_mode()
        ):
            return None
        if series_id == "":
            return key if self._curve_points else None
        # A limit that is unlimited or does not respond to the hook load has no series.
        return key if any(s["id"] == series_id for s in self._limit_series) else None

    @pyqtSlot(str, result=bool)
    def governingCaseAvailable(self, series_id: str) -> bool:
        return self._governing_case_chart(series_id) is not None

    @pyqtSlot(str, float)
    def showGoverningCase(self, series_id: str, outreach: float) -> None:
        """Find the case behind the point of ``series_id`` at ``outreach`` off the GUI
        thread, then apply it to the Scene and ask for the Scene tab."""
        key = self._governing_case_chart(series_id)
        doc = self._model.document
        if key is None or doc is None or self._shutting_down:
            return
        outreach_m = float(outreach)
        # The chart's own mode and limits: the case must reproduce the point drawn.
        worker = _GoverningCaseWorker(
            doc.model_copy(deep=True),
            key.hoist_id,
            key.mode,
            self._enabled_limits(),
            outreach_m,
            series_id or None,
        )
        worker.finishedWith.connect(lambda case, w=worker: self._on_case_finished(w, case))
        worker.failed.connect(lambda message, w=worker: self._on_case_failed(w, message))
        worker.finished.connect(lambda w=worker: self._threads.discard(w))
        worker.finished.connect(worker.deleteLater)
        self._case_request = _CaseRequest(
            worker, self._generation, key, outreach_m, self._status_text
        )
        self._threads.add(worker)
        self._set_status(f"Finding the governing case at {outreach_m:.1f} m...")
        worker.start()

    def _take_case_request(self, worker: _GoverningCaseWorker) -> Optional[_CaseRequest]:
        """The request ``worker`` ran for, if it still describes the chart on screen."""
        request = self._case_request
        if self._stopped() or request is None or request.worker is not worker:
            return None
        self._case_request = None
        if (
            request.generation != self._generation
            or request.key != self._displayed_key
            or request.key.hoist_id != self._model.selected_hoist_id
        ):
            # An edit, a new document or another hoist since the click: drop the result.
            if self._status_text.startswith("Finding the governing case"):
                self._set_status(request.previous_status)
            return None
        return request

    def _on_case_finished(self, worker: _GoverningCaseWorker, case: Any) -> None:
        request = self._take_case_request(worker)
        if request is None:
            return
        scene = self._scene_vm
        if case is None or scene is None:
            self._set_status(f"No governing case at {request.outreach_m:.1f} m")
            return
        name = self._limit_display_names().get(case.limit_id) or case.limit_id
        # Not a content change: that would clear the label the Scene shows.
        scene.apply_governing_case(case, f"Governing case: {name} at {request.outreach_m:.1f} m")
        if self._status_text.startswith("Finding the governing case"):
            self._set_status(request.previous_status)
        self.showSceneRequested.emit()

    def _on_case_failed(self, worker: _GoverningCaseWorker, message: str) -> None:
        request = self._take_case_request(worker)
        if request is None:
            return
        _LOG.warning("Governing case failed at %.1f m: %s", request.outreach_m, message)
        self._set_status(f"⚠ Governing case error: {message}")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @pyqtSlot(QUrl, result=bool)
    def exportCsv(self, url: QUrl) -> bool:
        if self._partial:
            self._set_status("Export unavailable while the chart is still computing")
            return False
        path = Path(url.toLocalFile() if url.isLocalFile() else url.toString())
        try:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["series", "outreach_m", "load_t"])
                for x, y in self._curve_points:
                    writer.writerow(["capacity", f"{x:.4f}", f"{y:.4f}"])
                for series in self._limit_series:
                    for x, y in series["points"]:
                        writer.writerow([series["label"], f"{x:.4f}", f"{y:.4f}"])
                for marker in self._markers:
                    writer.writerow(
                        [
                            f"contractual ({marker['status']})",
                            f"{marker['outreach']:.4f}",
                            f"{marker['load']:.4f}",
                        ]
                    )
        except OSError as exc:
            self._set_status(f"CSV export failed: {exc}")
            return False
        self._set_status(f"Exported {path.name}")
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_document_changed(self, _doc) -> None:
        self._generation += 1
        self._cache.clear()
        # The sweep in flight works on its own copy of the old document, so it can finish
        # safely; the generation check discards its result.
        self._cancel_all()
        # A cancelled worker may still be finishing with the old cache; it keeps its own
        # reference, so swap in a new one rather than clearing it under the worker.
        self._compute_cache = ComputeCache()
        self._compute_cache_fingerprint = None
        self.reload()

    def _on_content_changed(self) -> None:
        self._generation += 1
        self._cancel_all()
        if self._partial:
            # The cancelled stream no longer matches the document: clear it now rather
            # than when the worker notices the cancel.
            self._clear_display()
        self._set_stale(bool(self._model.document))
        self._update_busy()

    @pyqtSlot()
    def reload(self) -> None:
        hoist_ids = self.hoistIds
        if self._model.selected_hoist_id not in hoist_ids:
            if hoist_ids:
                self._model.select_payload_hoist(hoist_ids[0])
        self._refresh_limits_models()
        self._rebuild_contractual_model()
        self.hoistsChanged.emit()
        self.chartModeChanged.emit()
        self.preferencesChanged.emit()
        self._show_or_prioritize()
        if self._stale or not self._model.document:
            self._set_status("" if self._model.document else "No document loaded")
