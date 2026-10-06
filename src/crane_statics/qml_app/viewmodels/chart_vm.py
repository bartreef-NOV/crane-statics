"""Load chart view model: design limits, capacity sweep and plot series."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot

from crane_statics.presentation.formatters import (
    ConnectionFormatter,
    HoistFormatter,
    RopeFormatter,
    VesselAttitudeFormatter,
)
from crane_statics.core.document_edit import DocumentEditor, build_contractual_point
from crane_statics.core.limit_auto_set import (
    ConnectionAutoSetResult,
    RopeAutoSetResult,
    compute_required_connection_capacity_kN,
    compute_required_rope_capacity_kN,
)
from crane_statics.data.models import CraneDocument
from crane_statics.qml_app.session import SessionState
from crane_statics.core.sweep import SweepCancelled, run_capacity_sweep

from ..models.list_models import DictListModel

_LOG = logging.getLogger(__name__)

LIMIT_ROLES = ["limitId", "name", "unit", "maxValue", "limitEnabled", "tooltip"]
CONTRACTUAL_ROLES = ["outreach", "load", "allowable", "status"]

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


class _SweepWorker(QThread):
    """Runs the capacity-curve sweep off the GUI thread."""

    progress = pyqtSignal(str)
    finishedWith = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        doc: CraneDocument,
        hoist_id: str,
        enabled_limits: dict,
        outreach_step: float,
        limit_display_names: dict,
    ) -> None:
        super().__init__()
        self._args = (doc, hoist_id, enabled_limits, outreach_step, limit_display_names)

    def run(self) -> None:
        try:
            self.finishedWith.emit(
                run_capacity_sweep(
                    *self._args,
                    progress=self.progress.emit,
                    should_cancel=self.isInterruptionRequested,
                )
            )
        except SweepCancelled:
            self.cancelled.emit()
        except Exception as exc:  # worker boundary: report instead of crashing the thread
            self.failed.emit(str(exc))


class ChartViewModel(QObject):
    """Owns design limits, the sweep lifecycle and the rendered chart series."""

    hoistsChanged = pyqtSignal()
    chartModeChanged = pyqtSignal()
    statusChanged = pyqtSignal()
    limitsChanged = pyqtSignal()
    chartUpdated = pyqtSignal()
    contractualChanged = pyqtSignal()
    preferencesChanged = pyqtSignal()
    resetViewRequested = pyqtSignal()

    def __init__(self, session: SessionState, parent=None):
        super().__init__(parent)
        self._session = session
        self._model = session.model
        self._status_text = ""
        self._stale = False
        self._busy = False
        self._shutting_down = False
        self._outreach_step = 1.0
        self._worker: Optional[_SweepWorker] = None
        self._last_result: dict[str, Any] = {}
        self._condition_text = ""
        self._generation = 0

        self._curve_points: list[list[float]] = []
        self._limit_series: list[dict[str, Any]] = []
        self._markers: list[dict[str, Any]] = []

        self._rope_limits_model = DictListModel(LIMIT_ROLES, self)
        self._connection_limits_model = DictListModel(LIMIT_ROLES, self)
        self._contractual_model = DictListModel(CONTRACTUAL_ROLES, self)

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
        self._render_active_mode()

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
        self._rope_limits_model.set_rows(self._limit_rows("rope"))
        self._connection_limits_model.set_rows(self._limit_rows("connection"))
        self.limitsChanged.emit()

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

        dl.max_kN = float(auto.required_kN)
        dl.enabled = True
        self._model.mark_content_changed()
        self._set_status(f"Auto-set {dl.id} to {auto.required_kN:.1f} {unit}")
        self._refresh_limits_models()
        self._set_stale(True)

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
        rows = [
            {
                "outreach": f"{cp.outreach_m:.1f}",
                "load": f"{cp.load_t:.1f}",
                "allowable": "",
                "status": "pending",
            }
            for cp in self._contractual_points()
        ]
        self._contractual_model.set_rows(rows)
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
        worker = self._worker
        if worker is None:
            return
        worker.requestInterruption()
        worker.wait()
        self._worker = None

    # ------------------------------------------------------------------
    # Sweep
    # ------------------------------------------------------------------

    @pyqtSlot()
    def draw(self) -> None:
        if self._shutting_down:
            return
        doc = self._model.document
        if doc is None or not self._model.selected_hoist_id:
            self._set_status("No document loaded")
            return
        if self._busy:
            return

        self._busy = True
        self._set_status("Sweeping...")
        generation = self._generation
        analysis_doc = doc.model_copy(deep=True)
        worker = _SweepWorker(
            analysis_doc,
            self._model.selected_hoist_id,
            self._enabled_limits(),
            self._outreach_step,
            self._limit_display_names(),
        )
        worker.progress.connect(self._set_status)
        worker.finishedWith.connect(
            lambda result, expected_generation=generation: self._on_sweep_finished(
                result, expected_generation
            )
        )
        worker.failed.connect(
            lambda message, expected_generation=generation: self._on_sweep_failed(
                message, expected_generation
            )
        )
        worker.cancelled.connect(self._on_sweep_cancelled)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    @pyqtSlot()
    def _on_sweep_cancelled(self) -> None:
        self._busy = False
        self._worker = None
        if not self._shutting_down:
            self._set_status("Sweep cancelled")

    @pyqtSlot()
    def drawBlocking(self) -> None:
        """Synchronous sweep used by tests and headless runs."""
        doc = self._model.document
        if doc is None or not self._model.selected_hoist_id:
            return
        self._on_sweep_finished(
            run_capacity_sweep(
                doc,
                self._model.selected_hoist_id,
                self._enabled_limits(),
                self._outreach_step,
                self._limit_display_names(),
            ),
            self._generation,
        )

    def _on_sweep_finished(self, result: dict, generation: Optional[int] = None) -> None:
        self._busy = False
        self._worker = None
        if generation is None:
            generation = self._generation
        if generation != self._generation:
            self._set_stale(True)
            return
        self._last_result = result or {}
        # The generation matches, so the document still holds the attitude swept at.
        self._condition_text = self._chart_condition_text()
        self._set_stale(False)
        by_mode = self._last_result.get("n_points_by_mode") or {}
        if by_mode:
            self._set_status(
                "Done - " + ", ".join(f"{k}:{int(v)}" for k, v in by_mode.items()) + " points"
            )
        else:
            self._set_status(f"Done - {self._last_result.get('n_points', 0)} points")
        self._render_active_mode()

    def _on_sweep_failed(self, message: str, generation: Optional[int] = None) -> None:
        _LOG.warning("Chart sweep failed: %s", message)
        self._busy = False
        self._worker = None
        if generation is None:
            generation = self._generation
        if generation != self._generation:
            self._set_stale(True)
            return
        self._set_status("\u26a0 Sweep error")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_active_mode(self) -> None:
        modes = self._last_result.get("modes") or {}
        chart_mode = self._current_chart_mode()
        payload = modes.get(chart_mode)
        if payload is None and chart_mode == "normal":
            payload = modes.get(next(iter(modes), ""), None)
        payload = payload or {"curve_data": [], "contractual_results": [], "limit_series": []}

        self._curve_points = [[float(x), float(y)] for x, y in payload.get("curve_data", [])]
        self._limit_series = [
            {
                "id": str(limit_id),
                "label": str(label),
                "color": _LIMIT_COLORS[position % len(_LIMIT_COLORS)],
                "points": [[float(x), float(y)] for x, y in points],
            }
            for position, (limit_id, label, _rank, points) in enumerate(
                payload.get("limit_series", [])
            )
        ]

        self._markers = []
        contractual_rows = []
        for cp, allowable, passed in payload.get("contractual_results", []):
            status = "pending" if passed is None else ("pass" if passed else "fail")
            # The preference hides plot markers only; the table still lists every point.
            self._markers.append(
                {"outreach": float(cp.outreach_m), "load": float(cp.load_t), "status": status}
            )
            contractual_rows.append(
                {
                    "outreach": f"{cp.outreach_m:.1f}",
                    "load": f"{cp.load_t:.1f}",
                    "allowable": "-" if allowable is None else f"{float(allowable):.1f}",
                    "status": status,
                }
            )
        if contractual_rows:
            self._contractual_model.set_rows(contractual_rows)
            self.contractualChanged.emit()

        self.chartUpdated.emit()

    @pyqtProperty("QVariantList", notify=chartUpdated)
    def curvePoints(self) -> list:
        return self._curve_points

    @pyqtProperty(str, notify=chartUpdated)
    def conditionText(self) -> str:
        """What the drawn chart is rated for, e.g. the slew envelope on a tilted vessel."""
        return self._condition_text

    def _chart_condition_text(self) -> str:
        doc = self._model.document
        if doc is None:
            return ""
        motion = doc.environment.vessel_motion
        return VesselAttitudeFormatter.chart_condition_text(motion.heel_deg, motion.trim_deg)

    @pyqtProperty("QVariantList", notify=chartUpdated)
    def limitSeries(self) -> list:
        return self._limit_series

    @pyqtProperty("QVariantList", notify=chartUpdated)
    def markers(self) -> list:
        return self._markers

    @pyqtProperty("QVariantMap", notify=chartUpdated)
    def axisRanges(self) -> dict:
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
    # Export
    # ------------------------------------------------------------------

    @pyqtSlot(QUrl, result=bool)
    def exportCsv(self, url: QUrl) -> bool:
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
        self.reload()

    def _on_content_changed(self) -> None:
        self._generation += 1
        self._set_stale(bool(self._model.document))

    @pyqtSlot()
    def reload(self) -> None:
        hoist_ids = self.hoistIds
        if self._model.selected_hoist_id not in hoist_ids:
            if hoist_ids:
                self._model.select_payload_hoist(hoist_ids[0])
        self._last_result = {}
        self._curve_points = []
        self._limit_series = []
        self._markers = []
        self._refresh_limits_models()
        self._rebuild_contractual_model()
        self.hoistsChanged.emit()
        self.chartModeChanged.emit()
        self.preferencesChanged.emit()
        self.chartUpdated.emit()
        self._set_stale(bool(self._model.document))
        self._set_status("" if self._model.document else "No document loaded")
