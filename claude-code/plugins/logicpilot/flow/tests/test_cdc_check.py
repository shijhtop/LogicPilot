"""Tests for the rebuilt cdc-check stage (SpyGlass/Verilator dispatch)."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.cdc_check import (
    _detect_clocks,
    _parse_spyglass_cdc,
    _parse_verilator_cdc,
    _scan_rtl_clocks,
    run_cdc_check,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(tmp_path: Path, clocks: list[str] | None = None, src: list[str] | None = None) -> dict:
    cdc = {"clocks": clocks} if clocks is not None else {}
    return {
        "_root": tmp_path,
        "project": {"src": src or []},
        "cdc": cdc,
    }


def _write_sv(tmp_path: Path, name: str, content: str) -> Path:
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    f = src / name
    f.write_text(content)
    return f


# ---------------------------------------------------------------------------
# Clock detection
# ---------------------------------------------------------------------------

def test_explicit_clocks_from_config(tmp_path: Path) -> None:
    clocks = _detect_clocks(_cfg(tmp_path, clocks=["clk_sys", "clk_usb"]))
    assert clocks == ["clk_sys", "clk_usb"]


def test_rtl_scan_finds_two_clocks(tmp_path: Path) -> None:
    _write_sv(tmp_path, "top.sv",
              "always @(posedge clk_a) begin end\n"
              "always @(posedge clk_b) begin end\n")
    cfg = _cfg(tmp_path, src=["src/*.sv"])
    clocks = _scan_rtl_clocks(cfg)
    assert set(clocks) == {"clk_a", "clk_b"}


def test_rtl_scan_single_clock(tmp_path: Path) -> None:
    _write_sv(tmp_path, "top.sv", "always @(posedge clk) begin end\n")
    cfg = _cfg(tmp_path, src=["src/*.sv"])
    clocks = _scan_rtl_clocks(cfg)
    assert clocks == ["clk"]


def test_rtl_scan_negedge_counted(tmp_path: Path) -> None:
    _write_sv(tmp_path, "top.sv",
              "always @(posedge clk_sys) begin end\n"
              "always @(negedge clk_ddr) begin end\n")
    cfg = _cfg(tmp_path, src=["src/*.sv"])
    clocks = _scan_rtl_clocks(cfg)
    assert set(clocks) == {"clk_sys", "clk_ddr"}


def test_rtl_scan_empty_src(tmp_path: Path) -> None:
    clocks = _scan_rtl_clocks(_cfg(tmp_path))
    assert clocks == []


# ---------------------------------------------------------------------------
# Single-clock skip
# ---------------------------------------------------------------------------

def test_single_clock_config_skips(tmp_path: Path) -> None:
    out = run_cdc_check(_cfg(tmp_path, clocks=["clk"]))
    assert out["status"] == "skip"
    assert "single-clock" in out["reason"]
    assert out["clocks"] == ["clk"]


def test_no_clocks_found_skips(tmp_path: Path) -> None:
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "skip"


def test_single_clock_rtl_scan_skips(tmp_path: Path) -> None:
    _write_sv(tmp_path, "top.sv", "always @(posedge clk) q <= d;\n")
    out = run_cdc_check(_cfg(tmp_path, src=["src/*.sv"]))
    assert out["status"] == "skip"


# ---------------------------------------------------------------------------
# Verilator output parsing
# ---------------------------------------------------------------------------

def test_parse_verilator_cdc_two_warnings() -> None:
    log = (
        "%Warning-CDCRSTLOGIC: src/top.sv:42:5: Logic in clock domain reset path\n"
        "%Warning-CDCPULSESYN: src/top.sv:55:10: Pulse too short for synchronizer\n"
    )
    viols = _parse_verilator_cdc(log)
    assert len(viols) == 2
    assert viols[0]["rule"] == "CDCRSTLOGIC"
    assert viols[0]["file"] == "src/top.sv"
    assert viols[0]["line"] == 42
    assert viols[0]["severity"] == "high"
    assert viols[1]["rule"] == "CDCPULSESYN"


def test_parse_verilator_cdc_empty_log() -> None:
    assert _parse_verilator_cdc("") == []


def test_parse_verilator_cdc_ignores_non_cdc_warnings() -> None:
    log = "%Warning-UNUSED: top.sv:1:1: Signal unused\n"
    assert _parse_verilator_cdc(log) == []


# ---------------------------------------------------------------------------
# SpyGlass output parsing
# ---------------------------------------------------------------------------

def test_parse_spyglass_cdc_error_and_warning() -> None:
    log = (
        "Ac_unsync01  | Error   | Active | top.u_sync.q | Missing synchronizer\n"
        "Ac_glitch01  | Warning | Active | top.data_q   | Glitch on gated path\n"
    )
    viols = _parse_spyglass_cdc(log)
    assert len(viols) == 2
    assert viols[0]["rule"] == "Ac_unsync01"
    assert viols[0]["severity"] == "high"
    assert viols[1]["rule"] == "Ac_glitch01"
    assert viols[1]["severity"] == "medium"


def test_parse_spyglass_cdc_fatal_is_high() -> None:
    log = "Ac_unsync01  | Fatal   | Active | top.q | Bad crossing\n"
    viols = _parse_spyglass_cdc(log)
    assert viols[0]["severity"] == "high"


def test_parse_spyglass_cdc_empty_log() -> None:
    assert _parse_spyglass_cdc("") == []


# ---------------------------------------------------------------------------
# Multi-clock: blocked when no tool installed
# ---------------------------------------------------------------------------

def test_multi_clock_no_tool_blocked(tmp_path: Path) -> None:
    with patch("shutil.which", return_value=None):
        out = run_cdc_check(_cfg(tmp_path, clocks=["clk_a", "clk_b"]))
    assert out["status"] == "blocked"
    assert "sg_shell" in out["missing"]
    assert "verilator" in out["missing"]
    assert "install_hint" in out


# ---------------------------------------------------------------------------
# print_cmd dry-run (tool-agnostic)
# ---------------------------------------------------------------------------

def test_print_cmd_single_clock_still_skips(tmp_path: Path) -> None:
    out = run_cdc_check(_cfg(tmp_path, clocks=["clk"]), print_cmd=True)
    assert out["status"] == "skip"


def test_print_cmd_verilator_dry_run(tmp_path: Path) -> None:
    with patch("shutil.which", side_effect=lambda b: None if b == "sg_shell" else "/usr/bin/verilator"):
        out = run_cdc_check(_cfg(tmp_path, clocks=["clk_a", "clk_b"]), print_cmd=True)
    assert out["status"] == "dry-run"
    assert out["tool"] == "verilator"
    assert "cmd" in out


def test_print_cmd_spyglass_dry_run(tmp_path: Path) -> None:
    with patch("shutil.which", return_value="/opt/synopsys/sg_shell"):
        out = run_cdc_check(_cfg(tmp_path, clocks=["clk_a", "clk_b"]), print_cmd=True)
    assert out["status"] == "dry-run"
    assert out["tool"] == "spyglass"
    assert "cmd" in out
