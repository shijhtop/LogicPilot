"""Tests for v0.7b sim heuristics + LOGICPILOT_SEED gate (§4b.2 / §4b.3)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.diagnostics import (  # noqa: E402
    LOGICPILOT_SEED_MARKER_RE,
    sim_walltime_warnings,
    verification_failures,
    verification_warnings,
)


# --- §4b.2 #1: no observable activity ---------------------------------------

def test_no_observable_output_warns() -> None:
    log = "compilation done\nexit code 0\n"
    out = verification_warnings(log, {}, {})
    assert any("no observable activity" in w for w in out)


def test_observable_display_silences_warning() -> None:
    log = '$display("hello world");\nexit code 0\n'
    out = verification_warnings(log, {}, {})
    assert not any("no observable activity" in w for w in out)


def test_observable_uvm_info_silences_warning() -> None:
    log = "UVM_INFO src/tb.sv(42): Hello\n"
    out = verification_warnings(log, {}, {})
    assert not any("no observable activity" in w for w in out)


def test_empty_log_does_not_warn() -> None:
    """Empty log → no warning (caller will already see something else wrong)."""
    out = verification_warnings("", {}, {})
    assert not any("no observable activity" in w for w in out)


# --- §4b.2 #2: $urandom without LOGICPILOT_SEED marker ---------------------

def test_urandom_without_marker_warns() -> None:
    log = "$display(\"start\"); a = $urandom; $display(\"a=%0d\", a);\n"
    out = verification_warnings(log, {}, {})
    assert any("LOGICPILOT_SEED" in w for w in out)


def test_urandom_with_marker_silences_warning() -> None:
    log = (
        "LOGICPILOT_SEED=42\n"
        "$display(\"start\"); a = $urandom;\n"
    )
    out = verification_warnings(log, {}, {})
    assert not any("LOGICPILOT_SEED" in w for w in out)


def test_no_random_no_warning() -> None:
    log = "$display(\"deterministic test\");\n"
    out = verification_warnings(log, {}, {})
    assert not any("LOGICPILOT_SEED" in w for w in out)


# --- §4b.2 #3: wall-clock heuristic ----------------------------------------

def test_short_walltime_warns_when_no_cycles() -> None:
    out = sim_walltime_warnings(elapsed_s=0.05, metrics={})
    assert any("suspiciously fast" in w for w in out)


def test_short_walltime_silenced_by_high_cycle_count() -> None:
    out = sim_walltime_warnings(elapsed_s=0.05, metrics={"cycles": 5000})
    assert not any("suspiciously fast" in w for w in out)


def test_long_walltime_no_warning() -> None:
    out = sim_walltime_warnings(elapsed_s=2.5, metrics={})
    assert not any("suspiciously fast" in w for w in out)


def test_walltime_none_no_warning() -> None:
    """elapsed=None (e.g. timeout path) → skip heuristic; other code handles."""
    out = sim_walltime_warnings(elapsed_s=None, metrics={})
    assert out == []


# --- §4b.3: opt-in seed-log hard gate --------------------------------------

def test_require_seed_log_disabled_returns_no_failures() -> None:
    log = "a = $urandom;\n"  # urandom but no marker
    out = verification_failures(log, {}, {"verification": {"require_seed_log": False}})
    assert out == []


def test_require_seed_log_default_off_returns_no_failures() -> None:
    """Absent key → behaves like False (back-compat for existing flow.toml)."""
    log = "a = $urandom;\n"
    out = verification_failures(log, {}, {})
    assert out == []


def test_require_seed_log_true_with_urandom_no_marker_fails() -> None:
    log = "a = $urandom;\n"
    out = verification_failures(log, {}, {"verification": {"require_seed_log": True}})
    assert len(out) == 1
    assert "require_seed_log" in out[0]
    assert "LOGICPILOT_SEED" in out[0]


def test_require_seed_log_true_with_marker_passes() -> None:
    log = "LOGICPILOT_SEED=7\na = $urandom;\n"
    out = verification_failures(log, {}, {"verification": {"require_seed_log": True}})
    assert out == []


def test_require_seed_log_true_no_random_no_failure() -> None:
    """No randomization at all → marker is irrelevant; pass."""
    log = "$display(\"deterministic\");\n"
    out = verification_failures(log, {}, {"verification": {"require_seed_log": True}})
    assert out == []


# --- v0.9 §6.4: coverage_enforcement = "fail" ------------------------------

def test_coverage_enforcement_default_no_fail() -> None:
    """Default ('warn') keeps below-goal coverage out of the failure list."""
    out = verification_failures(
        log_text="",
        metrics={"branch_coverage_pct": 50.0},
        cfg={"verification": {"coverage_goal_pct": 90.0}},
    )
    assert out == []


def test_coverage_enforcement_fail_below_goal() -> None:
    out = verification_failures(
        log_text="",
        metrics={"branch_coverage_pct": 50.0},
        cfg={"verification": {"coverage_goal_pct": 90.0, "coverage_enforcement": "fail"}},
    )
    assert len(out) == 1
    assert "branch_coverage_pct" in out[0]
    assert "coverage_enforcement='fail'" in out[0]


def test_coverage_enforcement_fail_meets_goal_no_fail() -> None:
    out = verification_failures(
        log_text="",
        metrics={"branch_coverage_pct": 95.0},
        cfg={"verification": {"coverage_goal_pct": 90.0, "coverage_enforcement": "fail"}},
    )
    assert out == []


def test_coverage_enforcement_off_no_fail() -> None:
    out = verification_failures(
        log_text="",
        metrics={"branch_coverage_pct": 10.0},
        cfg={"verification": {"coverage_goal_pct": 90.0, "coverage_enforcement": "off"}},
    )
    assert out == []


# --- marker regex sanity ---------------------------------------------------

def test_marker_regex_matches_canonical_form() -> None:
    assert LOGICPILOT_SEED_MARKER_RE.search("LOGICPILOT_SEED=42")
    assert LOGICPILOT_SEED_MARKER_RE.search("prefix LOGICPILOT_SEED=0 suffix")


def test_marker_regex_rejects_typos() -> None:
    assert not LOGICPILOT_SEED_MARKER_RE.search("LOGIC_PILOT_SEED=42")
    assert not LOGICPILOT_SEED_MARKER_RE.search("LOGICPILOT_SEED= 42")  # space
    assert not LOGICPILOT_SEED_MARKER_RE.search("LOGICPILOT_SEED=abc")
