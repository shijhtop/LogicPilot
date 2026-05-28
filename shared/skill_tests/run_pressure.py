#!/usr/bin/env python3
"""Manual pressure-test harness for LogicPilot skills.

The static layer (``test_skill_guards.py``) verifies that each scenario's
``guards`` strings still appear in the target ``SKILL.md``. That catches
silent drift but cannot verify the agent actually *uses* the guard under
pressure. This script is the manual half of that loop:

1. **RED**: paste the scenario prompt into a fresh agent session that
   does NOT have the target skill loaded. Confirm the baseline-failure-
   mode bullets actually happen.
2. **GREEN**: do it again with the skill loaded. Confirm the
   guarded-behavior bullets actually happen.
3. **REFACTOR**: if (1) does not fail or (2) does not pass, the skill is
   wrong — edit ``shared/skills/<target>/SKILL.md`` and re-run.

Default behavior prints the scenario fields so a human can copy/paste
into whichever agent harness is convenient (Claude Code, Codex, raw API).
``--claude-cli`` dispatches through the ``claude`` CLI when it is on
PATH (no API key handling, no SDK dependency — just shells out).

Usage:

    python3 shared/skill_tests/run_pressure.py shared/skill_tests/scenarios/cdc-multibit-bus.md
    python3 shared/skill_tests/run_pressure.py --list
    python3 shared/skill_tests/run_pressure.py --claude-cli scenarios/cdc-multibit-bus.md

This is intentionally low-tech: no PyYAML, no subprocess piping of API
keys, no implicit network calls. The goal is a portable harness any
contributor can run, not a closed evaluation rig.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from conftest import (  # noqa: E402  (import after sys.path tweak)
    SCENARIOS_DIR,
    Scenario,
    discover_scenarios,
    load_scenario,
)


def _scenario_body(scenario: Scenario) -> str:
    """Return the markdown body (everything after the YAML front matter)."""
    text = scenario.path.read_text(encoding="utf-8")
    _, _, after = text.partition("---\n")
    _, _, body = after.partition("---\n")
    return body.strip()


def _print_scenario(scenario: Scenario) -> None:
    body = _scenario_body(scenario)
    print()
    print(f"# {scenario.title}")
    print(f"  scenario: {scenario.name}")
    print(f"  target skill: {scenario.target_skill}")
    print(f"  guards ({len(scenario.guards)}):")
    for g in scenario.guards:
        print(f"    - {g!r}")
    if scenario.gate_text:
        print(f"  gate_text ({len(scenario.gate_text)}):")
        for g in scenario.gate_text:
            print(f"    - {g!r}")
    print()
    print("-" * 72)
    print(body)
    print("-" * 72)


def _dispatch_claude_cli(scenario: Scenario) -> int:
    cli = shutil.which("claude")
    if cli is None:
        print(
            "error: 'claude' CLI not found on PATH. Install it or omit "
            "--claude-cli to print the scenario for manual paste.",
            file=sys.stderr,
        )
        return 2

    body = _scenario_body(scenario)
    # Pull just the "Scenario prompt" section as the user-facing prompt.
    prompt = body.split("## Scenario prompt", 1)[-1].split("##", 1)[0].strip()
    if not prompt:
        print(
            f"error: {scenario.path.name} has no '## Scenario prompt' "
            f"section; nothing to dispatch.",
            file=sys.stderr,
        )
        return 2

    framing = textwrap.dedent(
        f"""\
        You are being pressure-tested against scenario {scenario.name!r}
        (target skill: {scenario.target_skill}). Respond to the user
        prompt below as you normally would in a LogicPilot session. The
        human evaluator will then check your response against the
        scenario's expected guarded behaviors.

        USER PROMPT:
        {prompt}
        """
    )
    print(f"=== dispatching to `claude` for scenario {scenario.name!r} ===")
    proc = subprocess.run([cli], input=framing, text=True)
    return proc.returncode


def _list_scenarios() -> int:
    scenarios = discover_scenarios()
    if not scenarios:
        print(f"(no scenarios under {SCENARIOS_DIR})")
        return 1
    width = max(len(s.name) for s in scenarios)
    for s in scenarios:
        print(f"  {s.name:<{width}}  [{s.target_skill}]  {s.title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual pressure-test harness for LogicPilot skills."
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        help="path to a scenario file under scenarios/, or its bare name "
        "(e.g. 'cdc-multibit-bus').",
    )
    parser.add_argument(
        "--list", action="store_true", help="list all discovered scenarios"
    )
    parser.add_argument(
        "--claude-cli",
        action="store_true",
        help="dispatch the scenario prompt to the 'claude' CLI on PATH "
        "instead of printing it. Run twice — once with the skill "
        "disabled (RED), once enabled (GREEN) — and judge by hand.",
    )
    args = parser.parse_args(argv)

    if args.list:
        return _list_scenarios()

    if not args.scenario:
        parser.print_help()
        return 0

    # Accept either a path or a bare scenario name.
    candidate = Path(args.scenario)
    if not candidate.exists():
        candidate = SCENARIOS_DIR / f"{args.scenario}.md"
    if not candidate.exists():
        print(f"error: scenario not found: {args.scenario}", file=sys.stderr)
        return 2

    scenario = load_scenario(candidate)
    if args.claude_cli:
        return _dispatch_claude_cli(scenario)
    _print_scenario(scenario)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
