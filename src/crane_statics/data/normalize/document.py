"""Normalize raw document data into a runtime CraneDocument."""

from copy import deepcopy
from typing import Any

from ..authored_models import (
    AUTHORED_SCHEMA_MAJOR_VERSION,
    AUTHORED_SCHEMA_NAME,
    authored_schema_major,
)
from ..models import (
    CANONICAL_BODIES,
    CraneDocument,
    PRIMARY_NODE_DEFAULTS,
    payload_hoist_ids,
)
from .authored import _normalize_authored_document


def _is_authored_document(doc_data: dict[str, Any]) -> bool:
    schema = doc_data.get("schema")
    if not isinstance(schema, dict):
        return False
    return (
        schema.get("name") == AUTHORED_SCHEMA_NAME
        and authored_schema_major(schema.get("version")) == AUTHORED_SCHEMA_MAJOR_VERSION
    )


def normalize_document(doc_data: dict[str, Any]) -> CraneDocument:
    """
    Normalize an authored document into runtime form.

    This function:
    1. Fills in missing required fields with defaults
    2. Generates derived nodes
    3. Generates canonical connections
    4. Ensures canonical fixed-body order

    Args:
        doc_data: Raw parsed data from file

    Returns:
        Normalized CraneDocument ready for analysis
    """
    doc_data = deepcopy(doc_data)

    if "schema" in doc_data:
        if _is_authored_document(doc_data):
            doc_data = _normalize_authored_document(doc_data)
        else:
            schema_obj = doc_data.get("schema")
            schema = schema_obj if isinstance(schema_obj, dict) else {}
            found_name = schema.get("name")
            found_version = schema.get("version")
            raise ValueError(
                f"Only crane-statics schema major version {AUTHORED_SCHEMA_MAJOR_VERSION} is "
                f"supported for authored input; found name={found_name!r}, "
                f"version={found_version!r}"
            )

    # Ensure required root fields exist
    if "schema_version" not in doc_data:
        doc_data["schema_version"] = "1.0.0"
    if "model_type" not in doc_data:
        doc_data["model_type"] = "fixed_topology_crane_2d"
    if "metadata" not in doc_data:
        doc_data["metadata"] = {}
    if "environment" not in doc_data:
        doc_data["environment"] = {}
    if "bodies" not in doc_data:
        doc_data["bodies"] = []
    if "nodes" not in doc_data:
        doc_data["nodes"] = []
    if "ropes" not in doc_data:
        doc_data["ropes"] = []
    if "hoists" not in doc_data:
        doc_data["hoists"] = []

    # Normalize body order: canonical fixed bodies first
    canonical_bodies = CANONICAL_BODIES
    existing_ids = {b.get("id"): b for b in doc_data["bodies"]}
    normalized_bodies = []

    for body_id in canonical_bodies:
        if body_id in existing_ids:
            normalized_bodies.append(existing_ids[body_id])
        else:
            # Insert default empty body
            normalized_bodies.append({"id": body_id, "mass_points": [], "wind_areas": []})

    # Add non-canonical bodies
    for body in doc_data["bodies"]:
        if body.get("id") not in canonical_bodies:
            normalized_bodies.append(body)

    doc_data["bodies"] = normalized_bodies

    # Ensure canonical primary topology nodes exist (internal topology synthesis).
    node_ids = {n.get("id") for n in doc_data["nodes"]}
    for node_id, node_def in PRIMARY_NODE_DEFAULTS.items():
        if node_id in node_ids:
            continue
        doc_data["nodes"].append(
            {
                "id": node_id,
                "body": node_def["body"],
                "x_m": float(node_def["x_m"]),
                "z_m": float(node_def["z_m"]),
            }
        )

    # Normalize structural nodes - set body if missing for known topology nodes
    structural_nodes = {
        "boom_heel": "boom",
        "rear_base": "rear_leg",
        "rear_top": "rear_leg",
        "front_base": "front_leg",
        "front_top": "front_leg",
    }

    for node in doc_data["nodes"]:
        node_id = node.get("id")
        if node_id in structural_nodes and "body" not in node:
            node["body"] = structural_nodes[node_id]

    # Create derived nodes if missing
    derived_node_mappings = {
        "front_top": ("rear_top", "front_leg"),
        "platform_rear": ("rear_base", "platform"),
        "platform_front": ("front_base", "platform"),
        "platform_heel": ("boom_heel", "platform"),
    }

    node_ids = {n.get("id") for n in doc_data["nodes"]}
    node_by_id = {n.get("id"): n for n in doc_data["nodes"]}

    for derived_id, (source_id, target_body) in derived_node_mappings.items():
        if derived_id not in node_ids and source_id in node_by_id:
            source_node = node_by_id[source_id]
            doc_data["nodes"].append(
                {
                    "id": derived_id,
                    "body": target_body,
                    "x_m": source_node.get("x_m", 0.0),
                    "z_m": source_node.get("z_m", 0.0),
                    "local_x_m": source_node.get("local_x_m"),
                    "local_z_m": source_node.get("local_z_m"),
                }
            )

    # Parse and validate
    doc = CraneDocument(**doc_data)

    # Generate canonical connections (runtime only)
    doc.connections = generate_canonical_connections()

    derive_payload_hoist_rope_geometry(doc)

    return doc


def derive_payload_hoist_rope_geometry(doc: CraneDocument) -> None:
    """Fill each payload hoist's ``max_hook_travel_m`` and ``rope_length_m`` in place.

    Both are consequences of the hoist's ``lowest_hook_height_m``, so they are
    derived here rather than authored: a normalized document always carries them,
    whether it arrived through the authored reader or straight from a dict.

    ``calculation`` is imported lazily on purpose -- ``calculation.engine``
    imports this module, so a module-level import would close the cycle.
    """
    from ...calculation.rope_mass import derive_hook_geometry

    payload_ids = set(payload_hoist_ids(doc))
    if not payload_ids:
        return
    doc_dict = doc.model_dump()
    for hoist in doc.hoists:
        if hoist.id not in payload_ids:
            continue
        if hoist.lowest_hook_height_m is None:
            hoist.lowest_hook_height_m = 0.0
        derived = derive_hook_geometry(doc_dict, hoist.id, float(hoist.lowest_hook_height_m))
        if derived is None:
            continue
        hoist.max_hook_travel_m, hoist.rope_length_m = derived


def generate_canonical_connections() -> list[dict[str, Any]]:
    """Generate the canonical fixed-topology connections."""
    return [
        {"id": "platform_base", "type": "ground_fixed"},
        {"id": "rear_hinge", "type": "body_pin"},
        {"id": "front_hinge", "type": "body_pin"},
        {"id": "upper_hinge", "type": "body_pin"},
        {"id": "heel_point", "type": "body_pin"},
    ]
