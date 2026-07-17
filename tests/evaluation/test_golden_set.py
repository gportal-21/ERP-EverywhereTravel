"""Golden Set — suite pytest (ver golden_set.py para el diseño/justificación)."""
import pytest

from core.structured_output import parse_structured_output
from tests.evaluation.golden_set import GOLDEN_CASES


@pytest.mark.unit
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c.id for c in GOLDEN_CASES])
def test_golden_case(case):
    result = parse_structured_output(case.raw_output, case.model)

    if case.expect_valid:
        assert result is not None, f"{case.id}: se esperaba una salida válida ({case.description})"
        for field, expected in (case.expected_fields or {}).items():
            actual = getattr(result, field)
            assert actual == expected, f"{case.id}: campo '{field}' esperado={expected!r} obtenido={actual!r}"
    else:
        assert result is None, f"{case.id}: se esperaba que la validación fallara ({case.description})"
