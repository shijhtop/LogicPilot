"""Tests for the built-in report stage."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logicpilot_flow.report import run_report  # noqa: E402


def _cfg(tmp_path: Path) -> dict:
    return {"_root": tmp_path, "project": {"build_dir": "build"}}


def _write_log(tmp_path: Path, stage: str, content: str) -> Path:
    log_dir = tmp_path / "build" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{stage}.log"
    log.write_text(content)
    return log


def test_report_blocked_without_logs_dir(tmp_path: Path) -> None:
    out = run_report(_cfg(tmp_path))
    assert out["stage"] == "report"
    assert any("no build/logs" in w for w in out["warnings"])


def test_report_aggregates_synth_metrics(tmp_path: Path) -> None:
    _write_log(tmp_path, "synth", "Slice LUTs                |  1234 |     0 |    134600 |  0.92\n")
    out = run_report(_cfg(tmp_path))
    assert out["status"] == "pass"
    synth = [r for r in out["reports"] if r["stage"] == "synth"][0]
    assert synth["metrics"].get("luts") == 1234


def test_report_extracts_power_metrics_from_power_log(tmp_path: Path) -> None:
    """Regression for codex review P2: run_report() must pass
    stage_name=log.stem so power-only patterns enable when re-reading
    a power.log post-hoc. Without that, the existing log file would
    return {} and report would silently lose the power numbers."""
    _write_log(tmp_path, "power", (
        "Vivado power report\n"
        "| Total On-Chip Power (W)  | 1.234 |\n"
        "| Dynamic (W)              | 0.900 |\n"
        "| Device Static (W)        | 0.334 |\n"
    ))
    out = run_report(_cfg(tmp_path))
    assert out["status"] == "pass"
    power = [r for r in out["reports"] if r["stage"] == "power"][0]
    assert power["metrics"].get("total_power_w") == 1.234, (
        f"power metrics not extracted from power.log: {power['metrics']} "
        "(run_report probably forgot stage_name=log.stem)")
    assert power["metrics"].get("dynamic_power_w") == 0.900
    assert power["metrics"].get("static_power_w") == 0.334


def test_report_does_not_emit_power_metrics_on_synth_log(tmp_path: Path) -> None:
    """The stage-scoping defence must also hold inside report aggregation:
    a synth log that happens to contain the word 'Static' must not
    surface as static_power_w."""
    _write_log(tmp_path, "synth", "Static Timing Analysis enabled with 1234 endpoints\n")
    out = run_report(_cfg(tmp_path))
    synth = [r for r in out["reports"] if r["stage"] == "synth"][0]
    assert "static_power_w" not in synth["metrics"]
