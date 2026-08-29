import pytest

from crane_statics.core.limit_components import (
    KNOWN_LIMIT_COMPONENTS,
    LimitComponent,
    validate_limit_component,
)
from crane_statics.core.session_model import DesignLimit


def test_limit_component_enum_values_validate_and_normalize() -> None:
    assert validate_limit_component(LimitComponent.RESULTANT) == "resultant"
    assert validate_limit_component(" Fx ") == "Fx"


def test_design_limit_rejects_unknown_component() -> None:
    with pytest.raises(ValueError, match="Unsupported design-limit component"):
        DesignLimit(id="bad", kind="connection", entity_id="heel_point", component="unknown")


def test_component_enum_covers_all_registered_values() -> None:
    assert KNOWN_LIMIT_COMPONENTS == {component.value for component in LimitComponent}
