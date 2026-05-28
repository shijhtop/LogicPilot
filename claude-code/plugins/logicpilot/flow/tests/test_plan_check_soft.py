"""Tests for plan-check soft_mode + deprecation prefix (v0.6 C1+C2).

v0.6 introduces a deprecation cycle for plan-check:
- soft_mode=False (default): existing hard-fail behavior preserved for
  callers that explicitly want it (e.g. LOGICPILOT_STRICT=1 in CLI).
- soft_mode=True (selected by run_all in v0.6): would-be failures are
  demoted to status="pass" + per-finding warnings prefixed with
  [DEPRECATION-WILL-FAIL-IN-v0.7b], and a top-level `deprecation` field
  is always set so CI integrators can detect pending deprecation.

The prefix protocol is intentionally generic — subsequent deprecation
cycles (v0.9 coverage_enforcement, etc.) MUST reuse the same prefix
shape so CI integrators only need one grep pattern.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.plan_check import (  # noqa: E402
    DEPRECATION_NOTE,
    DEPRECATION_PREFIX,
    run_plan_check,
)


# Reuse content shapes from the existing plan_check test module.
LONG_PROSE = (
    "This block does foo. " * 30
    + "\nDecisions: reset is async, deassert sync. AXIL latency 2 cycles. "
    + "Failure mode on overflow: drop and set status flag. "
    + "All decisions came from explicit Q&A with the user."
)

PLAN_WITH_CHECKBOX = (
    "# plan\n\n## Phase 1\n"
    + "- [ ] rtl/foo_top.sv ← uarch.md \n"
    + "- [ ] tb/foo_tb.sv  ← uarch.md \n"
    "\nNotes: this is the resumable execution log; check items off as work\n"
    "completes so a dropped session can pick up by reading unchecked rows.\n"
    "Additional context follows the checkboxes to satisfy the size floor.\n"
)


def _write_block(tmp_path: Path, spec: str | None = None,
                 uarch: str | None = None, plan: str | None = None) -> None:
    d = tmp_path / "docs"
    d.mkdir(parents=True, exist_ok=True)
    if spec is not None:
        (d / "spec.md").write_text(spec)
    if uarch is not None:
        (d / "uarch.md").write_text(uarch)
    if plan is not None:
        (d / "plan.md").write_text(plan)


# --- Prefix protocol ----------------------------------------------------------

def test_deprecation_prefix_shape():
    """Prefix is [DEPRECATION-WILL-FAIL-IN-vX.Y] with milestone label."""
    assert DEPRECATION_PREFIX.startswith("[DEPRECATION-WILL-FAIL-IN-v")
    assert DEPRECATION_PREFIX.endswith("]")


def test_deprecation_note_is_actionable():
    """Note must reference both escape hatches."""
    assert "--no-plan-gate" in DEPRECATION_NOTE
    assert "LOGICPILOT_STRICT" in DEPRECATION_NOTE


# --- Soft mode behaviour ------------------------------------------------------

def test_default_is_hard_mode(tmp_path: Path) -> None:
    """No soft_mode kwarg → existing hard-fail behavior preserved."""
    # No docs at all → block scope hard fail.
    out = run_plan_check({"_root": tmp_path})
    assert out["status"] == "fail"
    assert "deprecation" not in out


def test_soft_mode_demotes_fail_to_pass(tmp_path: Path) -> None:
    """soft_mode=True turns would-be fail into pass + prefixed warnings."""
    out = run_plan_check({"_root": tmp_path}, soft_mode=True)
    assert out["status"] == "pass"
    assert "deprecation" in out
    assert "warnings" in out
    # Every demoted-warning carries the stable prefix.
    assert all(
        w.startswith(DEPRECATION_PREFIX) for w in out["warnings"]
    ), out["warnings"]


def test_soft_mode_one_warning_per_high_finding(tmp_path: Path) -> None:
    """Block scope with 3 missing docs → 3 prefixed warnings."""
    out = run_plan_check({"_root": tmp_path}, soft_mode=True)
    high_findings = [f for f in out["findings"] if f["severity"] == "high"]
    # spec.md, uarch.md, plan.md — 3 missing.
    assert len(high_findings) == 3
    assert len(out["warnings"]) == len(high_findings)


def test_soft_mode_passes_through_clean_pass(tmp_path: Path) -> None:
    """Valid docs → pass in both modes; soft_mode still advertises deprecation."""
    _write_block(
        tmp_path,
        spec=LONG_PROSE,
        uarch=LONG_PROSE,
        plan=PLAN_WITH_CHECKBOX,
    )
    out_hard = run_plan_check({"_root": tmp_path})
    out_soft = run_plan_check({"_root": tmp_path}, soft_mode=True)

    assert out_hard["status"] == "pass"
    assert "deprecation" not in out_hard

    assert out_soft["status"] == "pass"
    assert "deprecation" in out_soft
    # Clean pass must NOT emit any DEPRECATION-WILL-FAIL warning.
    soft_warnings = out_soft.get("warnings", [])
    assert not any(
        w.startswith("[DEPRECATION-WILL-FAIL-IN-") for w in soft_warnings
    ), soft_warnings


def test_soft_mode_preserves_findings(tmp_path: Path) -> None:
    """Demotion must not hide the underlying findings — agents still need them."""
    out_hard = run_plan_check({"_root": tmp_path})
    out_soft = run_plan_check({"_root": tmp_path}, soft_mode=True)
    assert out_hard["findings"] == out_soft["findings"]
    assert out_hard["summary"] == out_soft["summary"]


def test_soft_mode_warning_contains_finding_detail(tmp_path: Path) -> None:
    """Each prefixed warning must identify the file + rule so agents can act."""
    out = run_plan_check({"_root": tmp_path}, soft_mode=True)
    for w in out["warnings"]:
        assert w.startswith(DEPRECATION_PREFIX)
        # Strip prefix; rest should look like 'file:line rule — message'.
        body = w[len(DEPRECATION_PREFIX):].strip()
        assert ":" in body, f"warning missing file:line — {w}"
        assert "—" in body or "-" in body, f"warning missing rule/message separator — {w}"


def test_soft_mode_keeps_print_cmd_dry_run(tmp_path: Path) -> None:
    """print_cmd=True is independent of soft_mode — always returns dry-run."""
    out = run_plan_check({"_root": tmp_path}, print_cmd=True, soft_mode=True)
    assert out["status"] == "dry-run"
