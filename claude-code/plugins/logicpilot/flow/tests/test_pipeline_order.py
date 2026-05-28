"""Tests for STAGE_ORDER including plan-check (v0.6 C5).

plan-check goes at the head of the default pipeline. The v0.6
deprecation cycle makes it soft (warn instead of fail); v0.7b will
flip it to hard-fail. Either way, ordering it first ensures the
front-end chain sees the planning gate before audit / sim / synth.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.stages import BUILTIN_STAGES, STAGE_ORDER  # noqa: E402
from logicpilot_flow.runner import run_all  # noqa: E402


def test_plan_check_is_in_stage_order() -> None:
    assert "plan-check" in STAGE_ORDER


def test_plan_check_is_first_in_stage_order() -> None:
    """First position so the planning gate runs before any other stage."""
    assert STAGE_ORDER[0] == "plan-check"


def test_plan_check_still_in_builtin_stages() -> None:
    """C5 must not remove plan-check from BUILTIN_STAGES."""
    assert "plan-check" in BUILTIN_STAGES


def test_default_stage_order_unchanged_after_plan_check() -> None:
    """The rest of the chain must keep its existing order."""
    expected_tail = [
        "audit", "tb-audit", "lint", "sim", "synth",
        "pnr", "power", "gls", "lec", "report",
    ]
    assert STAGE_ORDER[1:] == expected_tail


def test_run_all_default_pipeline_includes_plan_check(tmp_path: Path) -> None:
    """Bare config (no _pipeline) uses STAGE_ORDER → plan-check runs."""
    cfg = {"_root": tmp_path, "_stages": {}}
    out = run_all(cfg)
    assert "plan-check" in out["pipeline"]


def test_pipeline_override_does_not_auto_inject_plan_check(tmp_path: Path) -> None:
    """[pipeline].order user override is respected — no force-insert."""
    cfg = {
        "_root": tmp_path,
        "_stages": {},
        "_pipeline": ["audit", "report"],  # user explicitly omitted plan-check
    }
    out = run_all(cfg)
    assert "plan-check" not in out["pipeline"]
