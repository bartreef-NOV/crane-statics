"""File I/O utilities for Crane Statics documents."""

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ..data import (
    CraneDocument,
    normalize_document,
    document_to_authored_form,
)


class DocumentIOError(Exception):
    """Raised when document I/O fails."""

    pass


_AUTHORED_SCHEMA_FILES = {
    "5.13.0": "crane-statics-v5.13.schema.json",
}


@lru_cache(maxsize=8)
def _load_schema_validator(schema_filename: str) -> Draft202012Validator:
    schema_resource = resources.files("crane_statics.schemas").joinpath(schema_filename)
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _validate_authored_schema(data: dict[str, Any]) -> None:
    schema_obj = data.get("schema")
    if not isinstance(schema_obj, dict):
        raise DocumentIOError("Authored input must include a schema object")
    if schema_obj.get("name") != "crane-statics":
        raise DocumentIOError("Only crane-statics authored input is supported")
    version = schema_obj.get("version")
    schema_filename = _AUTHORED_SCHEMA_FILES.get(str(version))
    if not schema_filename:
        raise DocumentIOError(f"Unsupported authored schema version {version!r}; expected '5.13.0'")
    validator = _load_schema_validator(schema_filename)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    first = errors[0]
    location = "/".join(str(p) for p in first.absolute_path)
    location_msg = f" at {location}" if location else ""
    raise DocumentIOError(f"Schema validation failed{location_msg}: {first.message}")


def load_document(path: Path) -> CraneDocument:
    """
    Load and normalize a crane document from disk.

    Args:
        path: Path to the JSON file

    Returns:
        Normalized CraneDocument

    Raises:
        DocumentIOError: If load or validation fails
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        raise DocumentIOError(f"Failed to read file: {e}")

    try:
        _validate_authored_schema(data)
        doc = normalize_document(data)
        return doc
    except DocumentIOError:
        raise
    except Exception as e:
        raise DocumentIOError(f"Failed to validate document: {e}")


def save_document(doc: CraneDocument, path: Path) -> None:
    """
    Save a document to disk in authored format.

    Args:
        doc: The document to save
        path: Target path

    Raises:
        DocumentIOError: If save fails
    """
    try:
        # Convert to authored form (remove derived fields, connections)
        authored_data = document_to_authored_form(doc)
        _validate_authored_schema(authored_data)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(authored_data, f, indent=2)
    except Exception as e:
        raise DocumentIOError(f"Failed to save document: {e}")


def create_default_document() -> CraneDocument:
    """Create a new default crane model from template."""
    default_data = {
        "schema": {
            "name": "crane-statics",
            "version": "5.13.0",
        },
        "metadata": {
            "name": "New Crane Model",
        },
        "model_definition": {
            "environment": {
                "gravity_m_s2": 9.81,
                "air_density_kg_m3": 1.225,
                "wind_profile_exponent": 0.143,
                "wind_reference_height_m_asl": 10.0,
                "mean_sealevel_z_m": -35.0,
                "max_wind_speed_m_s": 20.0,
            },
            "vessel_motion": {
                "accel_x_m_s2": 0.0,
                "accel_y_m_s2": 0.0,
                "accel_z_m_s2": 0.0,
                "pitch_angular_accel_rad_s2": 0.0,
                "roll_angular_accel_rad_s2": 0.0,
                "reference_x_m": 0.0,
                "reference_z_m": 0.0,
            },
            "boom_width_m": 1.0,
            "slewing_bearing_diameter_m": 1.0,
            "boom_heel": {"x_m": 0.0, "z_m": 0.0},
            "upper_hinge": {"x_m": 0.0, "z_m": 0.0},
            "rear_hinge": {"x_m": 0.0, "z_m": 0.0},
            "front_hinge": {"x_m": 0.0, "z_m": 0.0},
            "boom": {
                "mass_points": [],
                "wind_areas": [],
                "nodes": {
                    "mh_hook": {"u_m": 0.0, "w_m": 0.0},
                },
            },
            "rear_leg": {
                "mass_points": [],
                "wind_areas": [],
                "nodes": {},
            },
            "front_leg": {
                "mass_points": [],
                "wind_areas": [],
                "nodes": {},
            },
            "platform": {
                "mass_points": [],
                "wind_areas": [],
                "nodes": {},
            },
            "payload_hoists": {
                "MH": {
                    "rope_segments": [{"from": "boom_heel", "to": "mh_hook"}],
                    "support_node_id": "mh_hook",
                    "hook_daf": 1.0,
                    "offlead_deg": 0.0,
                    "sidelead_deg": 0.0,
                    "falls": 1,
                    "hook_mass_t": 0.0,
                    "contractual_points": [{"outreach_m": 0.0, "load_t": 0.0}],
                }
            },
            "boom_hoist": {
                "rope_segments": [{"from": "boom_heel", "to": "rear_top", "parts": 2}],
            },
        },
    }

    return normalize_document(default_data)
