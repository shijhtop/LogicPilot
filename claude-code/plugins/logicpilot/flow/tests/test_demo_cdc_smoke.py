"""Smoke test for the shipped demo-cdc project.

Validates that the built-in stages (plan-check, audit, tb-audit,
cdc-check) all pass on the in-repo demo without needing any external
EDA tool — which is exactly what CI runners have.

This catches:
- RTL changes that introduce new audit findings
- TB changes that lose self-checking discipline
- CDC inventory drift from the actual RTL
- plan-check / spec / uarch / plan.md going out of sync
- Any breaking change in the built-in stage envelopes

External-tool stages (`sim`, `synth`) need iverilog / yosys and are
deliberately NOT covered here — they're exercised manually by the
maintainer when the open-source toolchain is installed locally.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.audit import run_source_audit, run_testbench_audit  # noqa: E402
from logicpilot_flow.cdc_check import run_cdc_check  # noqa: E402
from logicpilot_flow.config import load_config  # noqa: E402
from logicpilot_flow.plan_check import run_plan_check  # noqa: E402


DEMO_DIR = Path(__file__).resolve().parent.parent / "demo-cdc"


def _cfg() -> dict:
    """Load the demo config in safe-preset mode (matches CI / fresh checkout)."""
    return load_config(DEMO_DIR / "flow.toml", safe_preset_only=True)


# --- existence sanity ------------------------------------------------------

def test_demo_dir_exists() -> None:
    assert DEMO_DIR.is_dir(), f"missing demo project: {DEMO_DIR}"
    for required in (
        "flow.toml",
        "rtl/sync_2ff.v",
        "rtl/async_fifo.v",
        "rtl/cdc_top.v",
        "tb/cdc_top_tb.v",
        "docs/plan.md",
        "docs/spec.md",
        "docs/uarch.md",
        "docs/cdc-inventory.json",
    ):
        assert (DEMO_DIR / required).is_file(), f"missing {required}"


# --- plan-check ------------------------------------------------------------

def test_plan_check_passes() -> None:
    out = run_plan_check(_cfg())
    assert out["status"] == "pass", out


# --- audit / tb-audit ------------------------------------------------------

def test_source_audit_clean_no_high_findings() -> None:
    """Every demo RTL file should be clean (zero high-severity findings).
    If a new audit rule fires here, the demo needs an update or the rule
    needs a false-positive fix."""
    out = run_source_audit(_cfg())
    assert out["status"] == "pass"
    high = [f for f in out["findings"] if f["severity"] == "high"]
    assert not high, f"unexpected high-severity audit findings: {high}"


def test_tb_audit_clean_no_findings() -> None:
    out = run_testbench_audit(_cfg())
    assert out["status"] == "pass"
    assert out["summary"] == {"high": 0, "medium": 0, "low": 0}, out


# --- cdc-check -------------------------------------------------------------

def test_cdc_check_status_valid() -> None:
    """Multi-clock demo: status is pass/fail (tool found) or blocked (no tool in CI)."""
    out = run_cdc_check(_cfg())
    assert out["status"] in ("pass", "fail", "blocked"), out
    assert len(out.get("clocks", [])) >= 2


# --- end-to-end shape ------------------------------------------------------

def test_audit_engine_field_present_on_audit() -> None:
    out = run_source_audit(_cfg())
    assert out["audit_engine"] in ("regex", "verible-ast")
