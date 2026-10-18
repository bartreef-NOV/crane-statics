"""Kinematics adapter: boom angle -> node positions.

Adapted from crane_app.solver.kinematics; field names changed to match
the rewrite's CraneDocument model (x_m, z_m, local_x_m, local_z_m).
"""

from __future__ import annotations

import math
from typing import Dict, Any, Tuple


class KinematicsAdapter:
    """Wrapper for boom geometry and node position calculations."""

    def __init__(self, doc_dict: Dict[str, Any]):
        """Accept a CraneDocument.model_dump() compatible dict."""
        self.doc = doc_dict
        self.nodes: Dict[str, Dict] = {n["id"]: n for n in doc_dict.get("nodes", [])}
        self.hoists: list = doc_dict.get("hoists", [])

        ground = self.nodes.get("platform_base")
        if ground is None:
            raise ValueError("Required node 'platform_base' not found")
        self.base_x = float(ground.get("x_m", 0.0))
        self.base_z = float(ground.get("z_m", 0.0))
        self._last_resolved: Tuple[float, Dict[str, Tuple[float, float]]] | None = None

    def compute_outreach(self, boom_angle_deg: float, hoist_id: str) -> float:
        hoist = next((h for h in self.hoists if h.get("id") == hoist_id), None)
        if hoist is None:
            raise ValueError(f"Hoist {hoist_id!r} not found")
        load_node_id = hoist.get("load_node_id")
        positions = self._resolve_nodes(boom_angle_deg)
        pos = positions.get(load_node_id)
        if pos is None:
            raise ValueError(f"Load node {load_node_id!r} not found")
        return pos[0]  # x-coordinate = outreach

    def outreach_to_angle(self, outreach_m: float, hoist_id: str) -> float | None:
        """Analytic inverse of compute_outreach; returns None when outreach is unreachable."""
        hoist = next((h for h in self.hoists if h.get("id") == hoist_id), None)
        if hoist is None:
            return None
        heel_x = float(self.nodes.get("boom_heel", {}).get("x_m", 0.0))
        # Walk below_node_id chain to reach a boom-local node
        nid = hoist.get("load_node_id")
        boom_node = None
        for _ in range(10):
            n = self.nodes.get(nid)
            if n is None:
                break
            if n.get("local_x_m") is not None:
                boom_node = n
                break
            parent = n.get("below_node_id")
            if not parent:
                break
            nid = parent
        if boom_node is None:
            return None
        U = float(boom_node["local_x_m"])
        W = float(boom_node.get("local_z_m") or 0.0)
        R = math.sqrt(U * U + W * W)
        if R < 1e-9:
            return None
        cos_val = (outreach_m - heel_x) / R
        if not (-1.0 <= cos_val <= 1.0):
            return None
        return math.degrees(math.acos(cos_val) - math.atan2(W, U))

    def compute_all_node_positions(self, boom_angle_deg: float) -> Dict[str, Dict[str, float]]:
        """Return {node_id: {"x": float, "z": float}} for all nodes."""
        raw = self._resolve_nodes(boom_angle_deg)
        return {nid: {"x": x, "z": z} for nid, (x, z) in raw.items()}

    def _resolve_nodes(self, boom_angle_deg: float) -> Dict[str, Tuple[float, float]]:
        """Node positions at ``boom_angle_deg``; the last angle is kept, a sweep re-asks for it."""
        cached = self._last_resolved
        if cached is None or cached[0] != boom_angle_deg:
            cached = self._last_resolved = (boom_angle_deg, self._compute_nodes(boom_angle_deg))
        return dict(cached[1])

    def _compute_nodes(self, boom_angle_deg: float) -> Dict[str, Tuple[float, float]]:
        angle_rad = boom_angle_deg * math.pi / 180.0

        boom_heel = self.nodes.get("boom_heel")
        if not isinstance(boom_heel, dict):
            raise ValueError("Required node 'boom_heel' not found")
        heel_x = float(boom_heel.get("x_m", 0.0))
        heel_z = float(boom_heel.get("z_m", 0.0))

        resolved: Dict[str, Tuple[float, float]] = {}

        # First pass: all non-hanging nodes, and boom-local nodes even if they
        # also have below_node_id
        for node_id, node in self.nodes.items():
            local_x = node.get("local_x_m")
            if node.get("body") == "boom" and local_x is not None:
                # Boom-local always takes priority over hanging resolution
                lx = float(local_x)
                lz = float(node.get("local_z_m") or 0.0)
                x = heel_x + lx * math.cos(angle_rad) - lz * math.sin(angle_rad)
                z = heel_z + lx * math.sin(angle_rad) + lz * math.cos(angle_rad)
                resolved[node_id] = (x, z)
            elif node.get("below_node_id") is not None:
                continue  # handled in second pass
            elif node.get("x_m") is not None:
                resolved[node_id] = (float(node["x_m"]), float(node.get("z_m", 0.0)))
            else:
                raise ValueError(f"Node {node_id!r} has no coordinates")

        # Second pass: only hanging nodes that were NOT already resolved in the first pass
        for node_id, node in self.nodes.items():
            ref_id = node.get("below_node_id")
            if ref_id is None:
                continue
            if node_id in resolved:
                continue  # already resolved as boom-local in first pass
            if ref_id not in resolved:
                raise ValueError(
                    f"Reference node {ref_id!r} not resolved for hanging node {node_id!r}"
                )
            rx, rz = resolved[ref_id]
            # Some authored inputs omit drop_m; runtime stores that as None.
            # Treat missing/None as the contract default of 1.0 m.
            drop_raw = node.get("hanging_drop_m")
            drop_m = 1.0 if drop_raw is None else float(drop_raw)
            resolved[node_id] = (rx, rz - drop_m)

        return resolved
