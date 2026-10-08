"""Hoist-centric authored input: reeving expansion, validation and save round trips."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from crane_statics.core.io import DocumentIOError, load_document, save_document
from crane_statics.data import normalize_document

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.yaml"))


def _authored() -> dict:
    return {
        "schema": {"name": "crane-statics", "version": "6.0.0"},
        "metadata": {"name": "Reeving"},
        "model_definition": {
            "environment": {
                "max_wind_speed_m_s": 20.0,
                "wind_profile_exponent": 0.143,
                "wind_reference_height_m_asl": 10.0,
                "mean_sealevel_z_m": -35.0,
            },
            "structure": {
                "boom_width_m": 1.0,
                "boom_heel": {"x_m": 8.5, "z_m": 8.0},
                "upper_hinge": {"x_m": -11.0, "z_m": 52.3},
                "rear_hinge": {"x_m": -11.0, "z_m": 7.7},
                "front_hinge": {"x_m": 6.87, "z_m": 7.7},
            },
            "boom_hoist": {
                "reeving": [{"node": "boom_heel"}, {"node": "rear_top", "parts": 4}],
            },
            "payload_hoists": {
                "MH": {
                    "reeving": [
                        {"node": "winch", "body": "platform", "x_m": -5.0, "z_m": 3.0},
                        {"node": "sheave", "body": "rear_leg", "x_m": -9.0, "z_m": 40.0},
                        {"node": "tip", "body": "boom", "u_m": 100.0, "w_m": -1.0, "parts": 2},
                    ],
                    "hook": {"mass_t": 5.0, "falls": 4, "daf": 1.1, "offlead_deg": 1.0},
                    "load_chart": [{"outreach_m": 30.0, "load_t": 100.0}],
                },
            },
        },
    }


def _nodes(doc) -> dict:
    return {n.id: n for n in doc.nodes}


def _segments(doc, hoist_id: str) -> list[tuple[str, str, int]]:
    hoist = next(h for h in doc.hoists if h.id == hoist_id)
    rope = next(r for r in doc.ropes if r.id == hoist.rope_id)
    return [(s.from_node_id, s.to_node_id, s.mult) for s in rope.segments]


def test_reeving_expands_to_prefixed_nodes_and_chained_segments():
    doc = normalize_document(_authored())

    nodes = _nodes(doc)
    assert {"mh_winch", "mh_sheave", "mh_tip"} <= set(nodes)
    assert nodes["mh_tip"].body == "boom"
    assert nodes["mh_sheave"].body == "rear_leg"
    hook = next(h for h in doc.hoists if h.id == "MH")
    assert hook.support_node_id == "mh_tip"
    assert _segments(doc, "MH")[:2] == [
        ("mh_winch", "mh_sheave", 1),
        ("mh_sheave", "mh_tip", 2),
    ]
    assert _segments(doc, "MH")[-1] == ("mh_tip", hook.load_node_id, 4)


def test_reeving_can_reference_primary_nodes():
    doc = normalize_document(_authored())

    assert _segments(doc, "BH") == [("boom_heel", "rear_top", 4)]


def test_explicit_support_node_hangs_the_hook_mid_path():
    data = _authored()
    data["model_definition"]["payload_hoists"]["MH"]["support_node"] = "sheave"

    doc = normalize_document(data)

    assert next(h for h in doc.hoists if h.id == "MH").support_node_id == "mh_sheave"


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda e: e.update(body="boom", u_m=1.0, w_m=1.0, x_m=1.0), "exactly u_m and w_m"),
        (lambda e: e.update(body="platform", u_m=1.0, w_m=1.0, x_m=None, z_m=None), "x_m and z_m"),
        (lambda e: e.update(parts=2), "first reeving entry"),
    ],
)
def test_reeving_entry_validation(mutate, message):
    data = _authored()
    mutate(data["model_definition"]["payload_hoists"]["MH"]["reeving"][0])

    with pytest.raises(ValueError, match=message):
        normalize_document(data)


def test_duplicate_local_node_definition_is_rejected():
    data = _authored()
    reeving = data["model_definition"]["payload_hoists"]["MH"]["reeving"]
    reeving.append(dict(reeving[1]))

    with pytest.raises(ValueError, match="defined twice"):
        normalize_document(data)


def test_hoist_ids_differing_only_by_case_are_rejected():
    data = _authored()
    hoists = data["model_definition"]["payload_hoists"]
    hoists["mh"] = deepcopy(hoists["MH"])

    with pytest.raises(ValueError, match="differ ignoring case"):
        normalize_document(data)


def test_hoist_node_colliding_with_shared_body_node_is_rejected():
    data = _authored()
    data["model_definition"]["platform"] = {"nodes": {"mh_winch": {"x_m": 0.0, "z_m": 0.0}}}

    with pytest.raises(ValueError, match="collides"):
        normalize_document(data)


def test_unknown_referenced_node_is_rejected():
    data = _authored()
    data["model_definition"]["payload_hoists"]["MH"]["reeving"].append({"node": "nowhere"})

    with pytest.raises(ValueError, match="unknown node"):
        normalize_document(data)


def test_shared_node_is_written_by_global_id_and_round_trips(tmp_path):
    data = _authored()
    md = data["model_definition"]
    md["platform"] = {"nodes": {"shared": {"x_m": -2.0, "z_m": 5.0}}}
    md["payload_hoists"]["AH"] = deepcopy(md["payload_hoists"]["MH"])
    md["payload_hoists"]["AH"]["reeving"][0] = {"node": "shared"}
    md["payload_hoists"]["MH"]["reeving"][0] = {"node": "shared"}
    path = tmp_path / "shared.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    doc = load_document(path)

    save_document(doc, tmp_path / "out.yaml")
    saved = yaml.safe_load((tmp_path / "out.yaml").read_text(encoding="utf-8"))

    assert saved["model_definition"]["platform"]["nodes"] == {"shared": {"x_m": -2.0, "z_m": 5.0}}
    assert saved["model_definition"]["payload_hoists"]["AH"]["reeving"][0] == {"node": "shared"}
    reloaded = load_document(tmp_path / "out.yaml")
    assert _segments(reloaded, "AH") == _segments(doc, "AH")


def test_non_chained_rope_round_trips_with_from(tmp_path):
    data = _authored()
    reeving = data["model_definition"]["payload_hoists"]["MH"]["reeving"]
    reeving.append({"node": "sheave", "from": "winch", "parts": 2})
    path = tmp_path / "branch.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    doc = load_document(path)

    save_document(doc, tmp_path / "out.yaml")

    assert _segments(load_document(tmp_path / "out.yaml"), "MH") == _segments(doc, "MH")


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.stem)
def test_examples_round_trip_byte_stable(example, tmp_path):
    doc = load_document(example)
    out = tmp_path / example.name

    save_document(doc, out)

    assert out.read_text(encoding="utf-8") == example.read_text(encoding="utf-8")
    assert load_document(out).model_dump() == doc.model_dump()


def test_pass_through_entry_without_node_is_rejected():
    data = _authored()
    data["model_definition"]["payload_hoists"]["MH"]["reeving"].append({})

    with pytest.raises(ValueError, match="neither body nor node"):
        normalize_document(data)


def test_omitted_node_auto_names_owned_entries():
    data = _authored()
    reeving = data["model_definition"]["payload_hoists"]["MH"]["reeving"]
    for entry in reeving:
        entry.pop("node", None)

    doc = normalize_document(data)

    nodes = _nodes(doc)
    assert {"mh_n1", "mh_n2", "mh_n3"} <= set(nodes)
    assert set(doc.auto_named_node_ids) >= {"mh_n1", "mh_n2", "mh_n3"}


def test_auto_naming_skips_names_already_used_explicitly():
    data = _authored()
    reeving = data["model_definition"]["payload_hoists"]["MH"]["reeving"]
    reeving[0]["node"] = "n1"
    del reeving[1]["node"]
    del reeving[2]["node"]

    doc = normalize_document(data)

    nodes = _nodes(doc)
    assert {"mh_n1", "mh_n2", "mh_n3"} <= set(nodes)
    assert set(doc.auto_named_node_ids) == {"mh_n2", "mh_n3"}


def test_auto_named_node_omits_node_key_on_save(tmp_path):
    data = _authored()
    reeving = data["model_definition"]["payload_hoists"]["MH"]["reeving"]
    for entry in reeving:
        entry.pop("node", None)
    path = tmp_path / "auto_named.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    doc = load_document(path)

    save_document(doc, tmp_path / "out.yaml")
    saved = yaml.safe_load((tmp_path / "out.yaml").read_text(encoding="utf-8"))

    mh_reeving = saved["model_definition"]["payload_hoists"]["MH"]["reeving"]
    assert all("node" not in entry for entry in mh_reeving)
    reloaded = load_document(tmp_path / "out.yaml")
    assert _segments(reloaded, "MH") == _segments(doc, "MH")


def test_pass_through_of_auto_named_node_keeps_explicit_node_on_save(tmp_path):
    data = _authored()
    reeving = data["model_definition"]["payload_hoists"]["MH"]["reeving"]
    del reeving[0]["node"]  # "winch" becomes auto-named "n1"
    reeving.append({"node": "n1", "from": "tip"})
    path = tmp_path / "passthrough.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    doc = load_document(path)

    save_document(doc, tmp_path / "out.yaml")
    saved = yaml.safe_load((tmp_path / "out.yaml").read_text(encoding="utf-8"))

    mh_reeving = saved["model_definition"]["payload_hoists"]["MH"]["reeving"]
    assert "node" not in mh_reeving[0]
    assert mh_reeving[-1]["node"] == "n1"


def test_v5_documents_are_rejected(tmp_path):
    data = _authored()
    data["schema"]["version"] = "5.13.0"
    path = tmp_path / "old.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(DocumentIOError, match="Unsupported authored schema version"):
        load_document(path)
