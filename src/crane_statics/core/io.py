"""File I/O utilities for Crane Statics documents."""

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..data import (
    CraneDocument,
    normalize_document,
    document_to_authored_form,
)
from ..data.authored_models import (
    AuthoredDocument,
    AUTHORED_SCHEMA_MAJOR_VERSION,
    AUTHORED_SCHEMA_NAME,
    EXAMPLE_DOCUMENT,
    authored_schema_major,
    format_authored_validation_error,
)


class DocumentIOError(Exception):
    """Raised when document I/O fails."""

    pass


_YAML_SUFFIXES = {".yaml", ".yml"}
_JSON_SUFFIXES = {".json"}


def _format_for_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in _JSON_SUFFIXES:
        return "json"
    if suffix in _YAML_SUFFIXES:
        return "yaml"
    raise DocumentIOError(f"Unsupported file extension {suffix!r}; expected .json, .yaml, or .yml")


class _StrictIntSafeLoader(yaml.SafeLoader):
    """SafeLoader without YAML 1.1's ambiguous octal/sexagesimal int forms.

    PyYAML's default int resolver reads a bare leading-zero number like
    ``020`` as octal (16) and a colon-separated number like ``1:20`` as
    sexagesimal (80). Authored crane input has no use for either notation,
    and silently resolving one as the other would turn a typo into a wrong
    engineering value with no error. Dropping those two forms leaves such
    input as a string, which pydantic then parses as plain decimal (e.g.
    ``int("020") == 20``) or rejects outright (e.g. ``"1:20"``).
    """


_StrictIntSafeLoader.yaml_implicit_resolvers = {
    first_char: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:int"]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_StrictIntSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(r"^[-+]?(?:0|[1-9][0-9_]*|0x[0-9a-fA-F_]+|0b[0-1_]+)$"),
    list("-+0123456789"),
)


_MAX_FLOW_WIDTH = 90


class _CompactSafeDumper(yaml.SafeDumper):
    """SafeDumper that writes mappings of plain scalars (coordinates, chart points, reeving
    entries) in flow style on one line when short, and everything else in block style."""


def _represent_mapping(dumper: yaml.SafeDumper, data: dict) -> yaml.MappingNode:
    flat = all(not isinstance(v, (dict, list, tuple)) for v in data.values())
    flat = flat and sum(len(f"{k}: {v}, ") for k, v in data.items()) <= _MAX_FLOW_WIDTH
    return dumper.represent_mapping("tag:yaml.org,2002:map", data, flow_style=flat or None)


_CompactSafeDumper.add_representer(dict, _represent_mapping)


def _validate_authored_schema(data: dict[str, Any]) -> None:
    schema_obj = data.get("schema")
    if not isinstance(schema_obj, dict):
        raise DocumentIOError("Authored input must include a schema object")
    if schema_obj.get("name") != AUTHORED_SCHEMA_NAME:
        raise DocumentIOError("Only crane-statics authored input is supported")
    version = schema_obj.get("version")
    if authored_schema_major(version) != AUTHORED_SCHEMA_MAJOR_VERSION:
        raise DocumentIOError(
            f"Unsupported authored schema version {version!r}; expected major version "
            f"{AUTHORED_SCHEMA_MAJOR_VERSION}"
        )
    try:
        AuthoredDocument.model_validate(data)
    except ValidationError as e:
        raise DocumentIOError(format_authored_validation_error(e))


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
    fmt = _format_for_suffix(path.suffix)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f) if fmt == "json" else yaml.load(f, Loader=_StrictIntSafeLoader)
    except (IOError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as e:
        raise DocumentIOError(f"Failed to read file: {e}")

    if not isinstance(data, dict):
        raise DocumentIOError("Document root must be a mapping/object")

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
    fmt = _format_for_suffix(path.suffix)
    try:
        # Convert to authored form (remove derived fields, connections)
        authored_data = document_to_authored_form(doc)
        _validate_authored_schema(authored_data)

        with open(path, "w", encoding="utf-8") as f:
            if fmt == "json":
                json.dump(authored_data, f, indent=2)
            else:
                yaml.dump(
                    authored_data,
                    f,
                    Dumper=_CompactSafeDumper,
                    sort_keys=False,
                    allow_unicode=True,
                    width=100,
                )
    except DocumentIOError:
        raise
    except Exception as e:
        raise DocumentIOError(f"Failed to save document: {e}")


def create_default_document() -> CraneDocument:
    """Create a new default crane model from AuthoredDocument's root-level example."""
    return normalize_document(deepcopy(EXAMPLE_DOCUMENT))
