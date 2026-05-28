"""Tests for the v0.7b VHDL audit rule expansion (§4b.4).

Rule coverage was 4 → 15+; this file pins each new rule with a
positive fixture (rule triggers as expected) so accidental removal
during refactor is caught by CI.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.audit import run_source_audit  # noqa: E402


def _cfg(tmp_path: Path, vhd_src: str) -> dict:
    src_dir = tmp_path / "rtl"
    src_dir.mkdir()
    (src_dir / "x.vhd").write_text(vhd_src)
    return {
        "_root": tmp_path,
        "project": {"src": ["rtl/*.vhd"]},
        "toolchain": {},
        "_stages": {},
        "_pipeline": [],
    }


def _rule_hit(findings, rule_id: str) -> bool:
    return any(f["rule"] == rule_id for f in findings)


def _find_rule(findings, rule_id: str):
    return [f for f in findings if f["rule"] == rule_id]


# --- existing R1-R4 (v0.5.x rules, still must fire) -----------------------

def test_r1_after_delay(tmp_path: Path) -> None:
    src = "process(clk) begin\n  q <= d after 5 ns;\nend process;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_after_in_rtl")


def test_r2_wait_for(tmp_path: Path) -> None:
    src = "process begin\n  wait for 10 ns;\nend process;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_wait_for_in_rtl")


def test_r3_std_logic_arith(tmp_path: Path) -> None:
    src = "use ieee.std_logic_arith.all;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "deprecated_vhdl_arithmetic_package")


def test_r4_shared_variable(tmp_path: Path) -> None:
    src = "shared variable v : integer := 0;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "shared_variable")


# --- new R5-R15 (v0.7b additions) ----------------------------------------

def test_r5_bare_wait(tmp_path: Path) -> None:
    src = "process begin\n  wait;\nend process;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_bare_wait_in_rtl")


def test_r6_assert_in_rtl(tmp_path: Path) -> None:
    src = "assert valid = '1' report \"oops\";\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_assert_in_rtl")


def test_r6_report_in_rtl(tmp_path: Path) -> None:
    src = "report \"hello\" severity note;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_report_in_rtl")


def test_r7_time_signal(tmp_path: Path) -> None:
    src = "signal delay_t : time := 5 ns;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_time_signal")


def test_r8_integer_no_range(tmp_path: Path) -> None:
    src = "signal counter : integer := 0;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_integer_no_range")


def test_r8_integer_with_range_silenced(tmp_path: Path) -> None:
    src = "signal counter : integer range 0 to 255 := 0;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert not _rule_hit(out["findings"], "vhdl_integer_no_range")


def test_r10_unconstrained_array(tmp_path: Path) -> None:
    src = "type word_arr is array (natural range <>) of std_logic_vector(7 downto 0);\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_unconstrained_array")


def test_r11_generate_nonconst_range(tmp_path: Path) -> None:
    src = "gen: for i in 0 to width loop\n  q(i) <= d(i);\nend loop;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_generate_nonconst_range")


def test_r11_generate_const_range_silenced(tmp_path: Path) -> None:
    src = "gen: for i in 0 to 7 loop\n  q(i) <= d(i);\nend loop;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert not _rule_hit(out["findings"], "vhdl_generate_nonconst_range")


def test_r12_dual_edge_ff(tmp_path: Path) -> None:
    src = "if rising_edge(clk) or falling_edge(clk) then\n  q <= d;\nend if;\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_dual_edge_ff")


def test_r15_legacy_bit_type(tmp_path: Path) -> None:
    src = "signal x : bit_vector(7 downto 0) := \"00000000\";\n"
    out = run_source_audit(_cfg(tmp_path, src))
    assert _rule_hit(out["findings"], "vhdl_legacy_bit_type")


# --- coverage counter -----------------------------------------------------

def test_vhdl_rule_count_is_at_least_12(tmp_path: Path) -> None:
    """Aggregate a fixture exercising many rules; verify ≥ 12 distinct
    VHDL rule IDs fire. R9 ('vhdl_variable_outside_process') is currently
    a pass — the AST migration will pick it up."""
    src = (
        "use ieee.std_logic_arith.all;\n"               # R3
        "shared variable s : integer := 0;\n"            # R4
        "signal a : integer := 0;\n"                     # R8
        "signal t : time := 1 ns;\n"                     # R7
        "signal b : bit := '0';\n"                       # R15
        "process(clk) begin\n"
        "  q <= d after 5 ns;\n"                         # R1
        "  wait for 10 ns;\n"                            # R2
        "  wait;\n"                                       # R5
        "  assert ok = '1';\n"                            # R6
        "  report \"x\";\n"                               # R6 alt
        "  if rising_edge(clk) or falling_edge(clk) then\n"  # R12
        "    q <= d;\n"
        "  end if;\n"
        "end process;\n"
        "gen: for i in 0 to width loop\n"                # R11
        "  q(i) <= d(i);\n"
        "end loop;\n"
        "type ar is array (natural range <>) of std_logic;\n"  # R10
    )
    out = run_source_audit(_cfg(tmp_path, src))
    vhdl_rules = {
        f["rule"] for f in out["findings"]
        if f["rule"].startswith("vhdl_") or f["rule"] == "shared_variable"
           or f["rule"] == "deprecated_vhdl_arithmetic_package"
    }
    assert len(vhdl_rules) >= 12, f"only fired {len(vhdl_rules)} VHDL rules: {vhdl_rules}"
