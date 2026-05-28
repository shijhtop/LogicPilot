"""Tests for the doctor health check (v0.7a §4a.2)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.doctor import (  # noqa: E402
    _check_python,
    _worst_status,
    run_doctor,
)


# --- worst_status precedence -------------------------------------------------

def test_worst_status_all_pass() -> None:
    assert _worst_status(["pass", "pass"]) == "pass"


def test_worst_status_warn_beats_pass() -> None:
    assert _worst_status(["pass", "warn"]) == "warn"


def test_worst_status_blocked_beats_warn() -> None:
    assert _worst_status(["warn", "blocked", "pass"]) == "blocked"


def test_worst_status_fail_beats_all() -> None:
    assert _worst_status(["fail", "blocked", "warn", "pass"]) == "fail"


def test_worst_status_empty() -> None:
    assert _worst_status([]) == "pass"


# --- python version check ----------------------------------------------------

def test_check_python_current_runtime_is_supported() -> None:
    """The CI matrix runs 3.10/3.11/3.12 — all must come back as pass."""
    row = _check_python()
    assert row["name"] == "python_version"
    assert row["status"] == "pass"


# --- run_doctor end-to-end ---------------------------------------------------

def test_run_doctor_missing_flow_toml(tmp_path: Path) -> None:
    """No flow.toml → fail on the flow_toml row + overall fail."""
    out = run_doctor(tmp_path / "does-not-exist.toml")
    assert out["stage"] == "doctor"
    assert out["status"] == "fail"
    flow_check = next(c for c in out["checks"] if c["name"] == "flow_toml")
    assert flow_check["status"] == "fail"
    assert "missing" in flow_check["detail"]


def test_run_doctor_with_minimal_valid_config(tmp_path: Path) -> None:
    """Minimal valid flow.toml + tools available → at least pass on python +
    flow_toml; trust + tools may warn/block depending on machine."""
    flow_toml = tmp_path / "flow.toml"
    flow_toml.write_text(
        '[project]\ntop = "m"\n'
        '[toolchain]\npreset = "yosys-nextpnr"\n'
    )
    out = run_doctor(flow_toml)
    assert out["stage"] == "doctor"
    assert out["status"] in ("pass", "warn", "blocked")
    names = [c["name"] for c in out["checks"]]
    assert "python_version" in names
    assert "flow_toml" in names
    assert "workspace_trust" in names
    assert "smoke_test" in names


def test_run_doctor_schema_typo_surfaces_warn(tmp_path: Path) -> None:
    """flow.toml with unknown top-level section → flow_toml row = warn,
    with schema warnings attached."""
    flow_toml = tmp_path / "flow.toml"
    flow_toml.write_text(
        '[project]\ntop = "m"\n'
        '[toolchain]\npreset = "yosys-nextpnr"\n'
        '[projct]\nfoo = 1\n'  # typo
    )
    out = run_doctor(flow_toml)
    flow_check = next(c for c in out["checks"] if c["name"] == "flow_toml")
    assert flow_check["status"] == "warn"
    assert "warnings" in flow_check
    assert any("projct" in w for w in flow_check["warnings"])


def test_run_doctor_summary_counts_match_checks(tmp_path: Path) -> None:
    flow_toml = tmp_path / "flow.toml"
    flow_toml.write_text(
        '[project]\ntop = "m"\n'
        '[toolchain]\npreset = "yosys-nextpnr"\n'
    )
    out = run_doctor(flow_toml)
    counts_by_status: dict[str, int] = {}
    for c in out["checks"]:
        counts_by_status[c["status"]] = counts_by_status.get(c["status"], 0) + 1
    for status in ("pass", "warn", "fail", "blocked"):
        assert out["summary"][status] == counts_by_status.get(status, 0)


def test_run_doctor_aggregates_install_hints(tmp_path: Path) -> None:
    """Blocked stages should contribute their install_hint into the
    top-level aggregated install_hint dict."""
    flow_toml = tmp_path / "flow.toml"
    flow_toml.write_text(
        '[project]\ntop = "m"\n'
        '[toolchain]\npreset = "yosys-nextpnr"\n'
        '[stages.synth]\n'
        'cmd = "yosys -V"\n'
        'name = "yosys"\n'
        'probes = ["yosys"]\n'
    )
    out = run_doctor(flow_toml)
    # If yosys happens to be installed on this machine, skip — we can't
    # force blocked state without mocking PATH.
    blocked = [c for c in out["checks"] if c.get("status") == "blocked"]
    if not blocked:
        return
    assert "install_hint" in out
    assert "yosys" in out["install_hint"]
