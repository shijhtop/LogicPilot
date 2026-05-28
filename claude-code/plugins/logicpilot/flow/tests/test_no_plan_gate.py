"""Tests for --no-plan-gate flag + LOGICPILOT_STRICT env (v0.6 C3+C4).

run_all gets two new kwargs:
- no_plan_gate=True → plan-check is removed from the pipeline entirely.
- strict_plan=True  → plan-check runs in hard-fail mode (preview the
  v0.7b behavior).

Default (no flags): plan-check runs in soft mode and warns instead of
failing. This is the v0.6 deprecation cycle's behavior.

Tests use an explicit [pipeline] order that includes plan-check, so
they remain valid regardless of whether C5 has landed (which adds
plan-check to the default STAGE_ORDER).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.runner import run_all, run_stage  # noqa: E402


def _cfg_with_plan_only(tmp_path: Path) -> dict:
    """Minimal config: only the built-in plan-check in the pipeline."""
    return {
        "_root": tmp_path,
        "_stages": {},
        "_pipeline": ["plan-check"],
        # audit/tb-audit/report auto-inject — they pass on empty source/tb lists.
    }


# --- run_all default --------------------------------------------------------

def test_default_includes_plan_check_in_hard_mode(tmp_path: Path) -> None:
    """v0.7b: default run_all puts plan-check in the pipeline AND runs it
    in hard-fail mode. The v0.6 soft-mode + deprecation prefix is gone."""
    out = run_all(_cfg_with_plan_only(tmp_path))
    assert "plan-check" in out["pipeline"]
    plan = next(r for r in out["results"] if r["stage"] == "plan-check")
    assert plan["status"] == "fail"
    # No deprecation field; no DEPRECATION-WILL-FAIL warnings either.
    assert "deprecation" not in plan
    assert not any(
        w.startswith("[DEPRECATION-WILL-FAIL-IN-")
        for w in plan.get("warnings", [])
    )


def test_strict_plan_is_no_op_in_v0_7b(tmp_path: Path) -> None:
    """LOGICPILOT_STRICT / strict_plan=True remain accepted for v0.6
    CI back-compat but are now no-ops (hard fail is the default)."""
    out_implicit = run_all(_cfg_with_plan_only(tmp_path))
    out_explicit = run_all(_cfg_with_plan_only(tmp_path), strict_plan=True)
    plan_a = next(r for r in out_implicit["results"] if r["stage"] == "plan-check")
    plan_b = next(r for r in out_explicit["results"] if r["stage"] == "plan-check")
    assert plan_a["status"] == plan_b["status"] == "fail"
    assert "deprecation" not in plan_a
    assert "deprecation" not in plan_b


# --- --no-plan-gate ---------------------------------------------------------

def test_no_plan_gate_removes_plan_check_from_pipeline(tmp_path: Path) -> None:
    """no_plan_gate=True → plan-check absent from pipeline list and results."""
    out = run_all(_cfg_with_plan_only(tmp_path), no_plan_gate=True)
    assert "plan-check" not in out["pipeline"]
    assert not any(r["stage"] == "plan-check" for r in out["results"])


def test_no_plan_gate_preserves_other_stages(tmp_path: Path) -> None:
    """no_plan_gate only removes plan-check, not other stages."""
    cfg = {
        "_root": tmp_path,
        "_stages": {},
        "_pipeline": ["plan-check", "report"],
    }
    out = run_all(cfg, no_plan_gate=True)
    assert "plan-check" not in out["pipeline"]
    assert "report" in out["pipeline"]


# --- --strict (LOGICPILOT_STRICT=1) -----------------------------------------

def test_strict_plan_hardens_plan_check(tmp_path: Path) -> None:
    """strict_plan=True → plan-check runs hard, returns fail without docs."""
    out = run_all(_cfg_with_plan_only(tmp_path), strict_plan=True)
    plan = next(r for r in out["results"] if r["stage"] == "plan-check")
    assert plan["status"] == "fail"
    # Hard mode = no deprecation field, no DEPRECATION-prefixed warnings.
    assert "deprecation" not in plan
    assert not any(
        w.startswith("[DEPRECATION-WILL-FAIL-IN-")
        for w in plan.get("warnings", [])
    )


def test_strict_plan_halts_pipeline_on_fail(tmp_path: Path) -> None:
    """When plan-check fails (strict), pipeline halts and report never runs."""
    cfg = {
        "_root": tmp_path,
        "_stages": {},
        # plan-check goes FIRST so audit/tb-audit don't run before it
        # (they auto-inject at position 0 unless already present).
        "_pipeline": ["plan-check", "audit", "tb-audit", "report"],
    }
    out = run_all(cfg, strict_plan=True)
    assert out["overall"] == "fail"
    # report should NOT have run because plan-check halted the chain.
    stages_run = [r["stage"] for r in out["results"]]
    assert "plan-check" in stages_run
    assert "report" not in stages_run


# --- run_stage soft_mode pass-through ----------------------------------------

def test_run_stage_default_is_hard_mode(tmp_path: Path) -> None:
    """Direct run_stage('plan-check', cfg) keeps hard-fail behavior."""
    out = run_stage("plan-check", {"_root": tmp_path})
    assert out["status"] == "fail"
    assert "deprecation" not in out


def test_run_stage_soft_mode_kwarg_demotes(tmp_path: Path) -> None:
    """run_stage('plan-check', cfg, soft_mode=True) demotes fail to pass."""
    out = run_stage("plan-check", {"_root": tmp_path}, soft_mode=True)
    assert out["status"] == "pass"
    assert "deprecation" in out


# --- flag interaction --------------------------------------------------------

def test_no_plan_gate_overrides_strict_plan(tmp_path: Path) -> None:
    """If plan-check is removed, strict_plan has nothing to harden."""
    out = run_all(
        _cfg_with_plan_only(tmp_path),
        no_plan_gate=True,
        strict_plan=True,
    )
    assert "plan-check" not in out["pipeline"]
    assert not any(r["stage"] == "plan-check" for r in out["results"])
