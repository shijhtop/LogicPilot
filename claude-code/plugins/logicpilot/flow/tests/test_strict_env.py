"""Tests for LOGICPILOT_STRICT env var parsing (v0.6 C3+C4).

The CLI exposes _strict_plan_from_env() to convert the env var into a
boolean; truthy values flip plan-check from soft (v0.6 default) to hard
(preview of v0.7b behavior). The helper is tested directly so we don't
have to spawn a subprocess for every env permutation.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.cli import _strict_plan_from_env  # noqa: E402


@pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "YES", "on"])
def test_truthy_values_enable_strict(monkeypatch, value: str) -> None:
    monkeypatch.setenv("LOGICPILOT_STRICT", value)
    assert _strict_plan_from_env() is True


@pytest.mark.parametrize("value", ["0", "false", "False", "no", "off", ""])
def test_falsy_values_disable_strict(monkeypatch, value: str) -> None:
    monkeypatch.setenv("LOGICPILOT_STRICT", value)
    assert _strict_plan_from_env() is False


def test_unset_env_disables_strict(monkeypatch) -> None:
    monkeypatch.delenv("LOGICPILOT_STRICT", raising=False)
    assert _strict_plan_from_env() is False


def test_arbitrary_string_is_falsy(monkeypatch) -> None:
    """Conservative default: only well-known truthy values activate strict."""
    monkeypatch.setenv("LOGICPILOT_STRICT", "maybe")
    assert _strict_plan_from_env() is False
