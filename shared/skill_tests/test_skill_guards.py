"""Static layer of the skill pressure tests.

For every scenario in ``scenarios/``, verify that the target skill's
``SKILL.md`` contains every string in the scenario's ``guards`` and
``gate_text`` lists. The agent-in-the-loop verification happens in
``run_pressure.py`` — this layer just prevents silent skill drift.
"""
from __future__ import annotations

import pytest

from conftest import Scenario, discover_scenarios


SCENARIOS = discover_scenarios()


def _scenario_id(s: Scenario) -> str:
    return f"{s.target_skill}::{s.name}"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_scenario_id)
def test_target_skill_exists(scenario: Scenario) -> None:
    assert scenario.skill_md.exists(), (
        f"{scenario.path.name}: target skill {scenario.target_skill!r} "
        f"has no SKILL.md at {scenario.skill_md}"
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_scenario_id)
def test_guards_present_in_skill(scenario: Scenario) -> None:
    """Every guard string MUST appear verbatim in the target SKILL.md."""
    text = scenario.skill_md.read_text(encoding="utf-8")
    missing = [g for g in scenario.guards if g not in text]
    assert not missing, (
        f"{scenario.path.name}: target skill {scenario.target_skill!r} "
        f"is missing guard strings that this scenario relies on:\n  - "
        + "\n  - ".join(repr(m) for m in missing)
        + f"\nEither restore the guards to {scenario.skill_md} or update "
        f"the scenario."
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_scenario_id)
def test_gate_text_present_in_skill(scenario: Scenario) -> None:
    """Every gate_text string MUST appear verbatim in the target SKILL.md.

    These are typically MUST / Definition of done markers that lock in the
    enforcement strength promised by the scenario's guarded behaviors.
    """
    text = scenario.skill_md.read_text(encoding="utf-8")
    missing = [g for g in scenario.gate_text if g not in text]
    assert not missing, (
        f"{scenario.path.name}: target skill {scenario.target_skill!r} "
        f"is missing gate_text strings:\n  - "
        + "\n  - ".join(repr(m) for m in missing)
        + f"\nThis usually means MUST language was softened in "
        f"{scenario.skill_md}. Restore it or remove the scenario."
    )


def test_scenarios_were_discovered() -> None:
    """Guard against an empty scenarios/ directory silently producing 0 tests."""
    assert SCENARIOS, (
        "No scenarios discovered under shared/skill_tests/scenarios/. "
        "If you removed them all, also remove this file."
    )
