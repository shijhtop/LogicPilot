"""Tests for /lp-tools readiness including built-in stages (v0.6 C6).

The F5c follow-up: previously discover_tools(cfg) only iterated declared
project stages, so plan-check / audit / tb-audit / report were absent
from the readiness output despite being always-available. v0.6 injects
them with status='runnable' + builtin=True flag so the agent sees them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.stages import BUILTIN_STAGES  # noqa: E402
from logicpilot_flow.tools import discover_tools  # noqa: E402


def _minimal_cfg(tmp_path: Path) -> dict:
    return {
        "_root": tmp_path,
        "_stages": {},
        "toolchain": {},
    }


def test_discover_tools_no_cfg_returns_tool_groups_only() -> None:
    """Without cfg: only tool_groups, no stages section."""
    out = discover_tools()
    assert "tool_groups" in out
    assert "stages" not in out


def test_discover_tools_with_cfg_includes_all_builtin_stages(tmp_path: Path) -> None:
    """With cfg: every BUILTIN_STAGES entry appears in out['stages']."""
    out = discover_tools(_minimal_cfg(tmp_path))
    assert "stages" in out
    for name in BUILTIN_STAGES:
        assert name in out["stages"], f"built-in {name!r} missing from readiness"


def test_builtin_stages_are_runnable(tmp_path: Path) -> None:
    """Built-ins run with no external tool → status='runnable' always.

    Exception: stages in BUILTIN_STAGES_NEEDING_TOOL MAY be 'blocked'
    when their required tool is missing — the contract there is
    install_hint + missing.
    """
    from logicpilot_flow.stages import BUILTIN_STAGES_NEEDING_TOOL
    out = discover_tools(_minimal_cfg(tmp_path))
    for name in BUILTIN_STAGES:
        if name in BUILTIN_STAGES_NEEDING_TOOL:
            assert out["stages"][name]["status"] in ("runnable", "blocked")
            if out["stages"][name]["status"] == "blocked":
                assert "missing" in out["stages"][name]
        else:
            assert out["stages"][name]["status"] == "runnable"


def test_builtin_stages_carry_builtin_flag(tmp_path: Path) -> None:
    """Agents need to distinguish built-ins from project-declared stages."""
    out = discover_tools(_minimal_cfg(tmp_path))
    for name in BUILTIN_STAGES:
        assert out["stages"][name].get("builtin") is True


def test_builtin_tool_name_matches_convention(tmp_path: Path) -> None:
    """Tool name 'built-in-<stage>' matches the run_stage internal handlers."""
    out = discover_tools(_minimal_cfg(tmp_path))
    for name in BUILTIN_STAGES:
        tool = out["stages"][name].get("tool", "")
        assert tool.startswith("built-in"), f"{name}: tool={tool!r}"


def test_project_stages_still_listed(tmp_path: Path) -> None:
    """Built-in injection must not hide declared project stages."""
    cfg = {
        "_root": tmp_path,
        "_stages": {
            "synth": {"cmd": "echo synth", "name": "echo"},
        },
        "toolchain": {},
    }
    out = discover_tools(cfg)
    # synth (project) + 4 built-ins = 5 entries minimum
    assert "synth" in out["stages"]
    assert all(b in out["stages"] for b in BUILTIN_STAGES)


def test_plan_check_visible_in_lp_tools_output(tmp_path: Path) -> None:
    """The F5c regression fix: plan-check must show up in /lp-tools."""
    out = discover_tools(_minimal_cfg(tmp_path))
    assert "plan-check" in out["stages"]
    assert out["stages"]["plan-check"]["status"] == "runnable"
    assert out["stages"]["plan-check"].get("builtin") is True
