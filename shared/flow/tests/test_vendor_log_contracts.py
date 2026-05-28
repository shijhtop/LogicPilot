"""Contract tests for vendor log parsing.

Reads the golden fixtures under ``fixtures/vendor_logs/`` and asserts our
parsers extract the expected fields with sensible types and values. Acts
as a regression net for vendor-format drift: when SBY / Vivado / Yosys /
nextpnr upgrade and tweak their output, these tests catch the breakage
*before* the envelope silently reports None / wrong numbers.

How to read failures:

- "missing key X" — regex no longer matches the new format. Inspect the
  fixture's surrounding lines vs the regex in metrics.py / formal.py.
- "value out of expected range" — extracted, but unit / scale wrong
  (e.g. mW vs W). Check the unit coercion path.
- "extra key Y" — regex now matches something it shouldn't (false
  positive); tighten the pattern.

DO NOT just edit the fixture to silence a failure — verify the parser is
right for the new format first, then refresh the fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logicpilot_flow.metrics import parse_metrics  # noqa: E402
from logicpilot_flow import formal  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vendor_logs"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


# --- Vivado synth ---------------------------------------------------------

def test_vivado_synth_extracts_utilization_and_wns() -> None:
    log = _read("vivado_synth.log")
    m = parse_metrics(log, {}, stage_name="synth")

    # Utilization must be picked up from the table form.
    assert m.get("luts") == 1234, f"LUTs wrong: got {m.get('luts')}"
    assert m.get("ffs") == 2345, f"FFs wrong: got {m.get('ffs')}"
    assert m.get("bram") == 8, f"BRAM wrong: got {m.get('bram')}"
    assert m.get("dsp") == 4, f"DSP wrong: got {m.get('dsp')}"

    # Timing summary line: "Worst Negative Slack:     -1.234 ns".
    # Even with "WNS-related items reported across 7 clocks" earlier in
    # the log (a trap that would steal the value as `7` without the
    # `\bWNS\b` word boundary), the real WNS value must be returned.
    assert "wns_ns" in m, "WNS not extracted from Vivado summary form"
    assert m["wns_ns"] == -1.234, (
        f"WNS sign / value wrong: got {m['wns_ns']} "
        "(possibly captured `7` from 'WNS-related items' trap)")

    # Power patterns must NOT fire on synth log even though it contains
    # words like "Logic". That was the regression bug.
    for forbidden in ("total_power_w", "dynamic_power_w", "static_power_w",
                      "logic_power_w", "bram_power_w", "dsp_power_w"):
        assert forbidden not in m, (
            f"power pattern '{forbidden}' leaked into synth log "
            f"(false-positive bug regressed)")


# --- Vivado power ---------------------------------------------------------

def test_vivado_power_extracts_all_buckets() -> None:
    log = _read("vivado_power.log")
    m = parse_metrics(log, {}, stage_name="power")

    # Total / dynamic / static — the headline numbers.
    assert m.get("total_power_w") == 1.234, f"total: {m.get('total_power_w')}"
    assert m.get("dynamic_power_w") == 0.900, f"dynamic: {m.get('dynamic_power_w')}"
    assert m.get("static_power_w") == 0.334, f"static: {m.get('static_power_w')}"

    # Per-bucket breakdown — assert exact values so silent regex
    # mis-matches (e.g. capturing junction temperature as io_power) get
    # caught, not just out-of-range ones.
    expected = {
        "clock_power_w":  0.105,
        "signal_power_w": 0.231,
        "logic_power_w":  0.187,
        "bram_power_w":   0.072,
        "dsp_power_w":    0.041,
        "io_power_w":     0.264,
    }
    for key, want in expected.items():
        assert key in m, f"missing power bucket: {key}"
        assert m[key] == want, f"{key} wrong: got {m[key]}, expected {want}"

    # Budget + margin + Tj.
    assert m.get("power_budget_w") == 1.500
    assert m.get("power_margin_w") == 0.266
    assert m.get("junction_temp_c") == 47.8


def test_vivado_power_patterns_skipped_without_stage_name() -> None:
    """Same log fed without stage_name='power' must NOT extract power
    metrics — that's the stage-scoping guard."""
    log = _read("vivado_power.log")
    m = parse_metrics(log, {})  # no stage_name
    for forbidden in ("total_power_w", "dynamic_power_w", "static_power_w"):
        assert forbidden not in m, (
            f"power pattern fired without stage_name='power': {forbidden}")


def test_vivado_power_with_traps_still_extracts_correct_values() -> None:
    """Same headline numbers + per-bucket values as the clean fixture,
    but surrounded by trap lines that would tempt unbounded bare-word
    regexes: 'Static Timing Analysis' (would steal static_power_w),
    'Clock Network: 24' (would steal clock_power_w as 24), 'Logical
    Analyzer' (would steal logic_power_w), 'Multiplier blocks: 4'
    (would steal dsp_power_w as 4), 'Dynamic Voltage Scaling: ...'
    (would steal dynamic_power_w), 'Statically-driven nets: 256'
    (would steal static_power_w as 256).

    All of these regressed before the \\b word-boundary fix. This test
    is the regression net."""
    log = _read("vivado_power_with_traps.log")
    m = parse_metrics(log, {}, stage_name="power")

    # Headlines unchanged.
    assert m.get("total_power_w") == 1.234
    assert m.get("dynamic_power_w") == 0.900, (
        f"dynamic regressed: got {m.get('dynamic_power_w')} "
        f"(probably from 'Dynamic Voltage Scaling')")
    assert m.get("static_power_w") == 0.334, (
        f"static regressed: got {m.get('static_power_w')} "
        f"(probably from 'Static Timing Analysis' or 'Statically-driven')")
    assert m.get("junction_temp_c") == 47.8, (
        f"junction temp regressed: got {m.get('junction_temp_c')}")

    # Per-bucket — every one of these has a confounding trap line above.
    expected = {
        "clock_power_w":  0.105,
        "signal_power_w": 0.231,
        "logic_power_w":  0.187,
        "bram_power_w":   0.072,
        "dsp_power_w":    0.041,
        "io_power_w":     0.264,
    }
    for key, want in expected.items():
        assert m.get(key) == want, (
            f"{key} captured wrong value {m.get(key)} (expected {want}); "
            "a trap-line word probably regressed the boundary fix")


# --- Yosys synth (open-source) -------------------------------------------

def test_yosys_synth_ice40_extracts_cells() -> None:
    log = _read("yosys_synth_ice40.log")
    m = parse_metrics(log, {}, stage_name="synth")

    # The yosys stat block lists SB_DFF / SB_LUT4 / SB_RAM rows.
    assert m.get("luts") == 189, f"LUTs (SB_LUT4): {m.get('luts')}"
    assert m.get("ffs") == 42, f"FFs (SB_DFF): {m.get('ffs')}"
    assert m.get("bram") == 1, f"BRAM (SB_RAM40_4K): {m.get('bram')}"

    # No DSP on this design — but ABSENT key (not None) is the contract.
    assert "dsp" not in m, "DSP wrongly extracted from yosys log with no DSP rows"


# --- nextpnr route -------------------------------------------------------

def test_nextpnr_extracts_fmax() -> None:
    log = _read("nextpnr_route.log")
    m = parse_metrics(log, {}, stage_name="pnr")

    # "Max frequency for clock 'wr_clk': 112.34 MHz" — first one wins
    # in the default behaviour.
    assert m.get("fmax_mhz") == 112.34, f"fmax: {m.get('fmax_mhz')}"


# --- Coverage report (mixed simulator + prose traps) ---------------------

def test_coverage_report_extracts_all_metrics_despite_prose_traps() -> None:
    """The fixture deliberately includes 'Coverage estimated for 12
    testcases across 4 regressions' BEFORE the actual percentages.
    Without the letter-forbidding gap, the regex would capture 12 (or
    4) as the coverage metric. With the gap forbidding letters between
    label and number, the regex skips the prose and lands on the real
    percentage line."""
    log = _read("coverage_report.log")
    m = parse_metrics(log, {}, stage_name="sim")

    expected = {
        "functional_coverage_pct": 92.40,
        "code_coverage_pct":       87.15,
        "line_coverage_pct":       91.20,
        "branch_coverage_pct":     84.50,
        "toggle_coverage_pct":     78.30,
        "fsm_coverage_pct":        96.10,
        "assertion_coverage_pct":  99.05,
    }
    for key, want in expected.items():
        assert key in m, f"missing coverage key: {key}"
        assert m[key] == want, (
            f"{key} wrong: got {m[key]}, expected {want} "
            "(possibly captured a prose number like '12 testcases')")


# --- SBY: pass path ------------------------------------------------------

def test_sby_pass_log_parses_clean() -> None:
    log = _read("sby_pass.log")
    properties, cex, engine_used = formal._parse_sby_output(log, Path("/tmp/work"))

    assert engine_used == "smtbmc z3", f"engine: {engine_used}"
    assert properties == {"<all>": "PASS"}, f"props: {properties}"
    assert cex == [], f"unexpected cex: {cex}"


# --- SBY: fail with per-assertion depth ----------------------------------

def test_sby_fail_log_parses_two_assertions_with_distinct_depths() -> None:
    """Multi-failure log: each cex must carry its OWN nearest step,
    not the first failure's step. Regression for the bug fixed in the
    code-review round."""
    log = _read("sby_fail_with_depth.log")
    properties, cex, engine_used = formal._parse_sby_output(log, Path("/tmp/work"))

    assert engine_used == "smtbmc z3"
    assert properties.get("fifo_no_overflow") == "FAIL"
    assert properties.get("arbiter_fairness") == "FAIL"
    assert len(cex) == 2

    by_prop = {c["property"]: c for c in cex}
    assert by_prop["fifo_no_overflow"]["depth_hit"] == 3, (
        f"fifo cex depth: {by_prop['fifo_no_overflow']['depth_hit']}")
    assert by_prop["arbiter_fairness"]["depth_hit"] == 7, (
        f"arbiter cex depth: {by_prop['arbiter_fairness']['depth_hit']}")

    # Trace path is rebased under work_dir when relative.
    assert by_prop["fifo_no_overflow"]["trace"].endswith("engine_0/trace0.vcd")
    assert by_prop["arbiter_fairness"]["trace"].endswith("engine_0/trace1.vcd")


# --- SBY: unknown verdict ------------------------------------------------

def test_sby_assert_without_name_parens_synthesizes_label() -> None:
    """Older SBY versions emit `Assert failed in mod: file:line` with no
    `(name)` parens. The parser must synthesize a stable name from
    module@file:line so the property key isn't lost. Also exercises the
    absolute-trace-path branch — the path must NOT be doubly prefixed
    with work_dir."""
    log = _read("sby_assert_no_name.log")
    properties, cex, engine_used = formal._parse_sby_output(
        log, Path("/tmp/work"))

    # Synthetic name: "<module>@<file>:<line>"
    assert "fifo@rtl/checks.sv:42" in properties, (
        f"synthetic name missing: {list(properties.keys())}")
    assert properties["fifo@rtl/checks.sv:42"] == "FAIL"
    assert engine_used == "smtbmc z3"

    # Counterexample's trace path is absolute → keep it as-is, do NOT
    # join with work_dir (would produce "/tmp/work/abs/path/...").
    assert len(cex) == 1
    assert cex[0]["trace"] == "/abs/path/engine_0/trace.vcd", (
        f"absolute trace path double-prefixed: {cex[0]['trace']}")
    assert cex[0]["depth_hit"] == 4


def test_sby_unknown_backfills_synthetic_all_entry() -> None:
    """DONE(UNKNOWN) with no per-property breakdown must backfill
    properties={<all>: UNKNOWN} so summary doesn't lie."""
    log = _read("sby_unknown.log")
    properties, cex, engine_used = formal._parse_sby_output(log, Path("/tmp/work"))

    assert engine_used == "smtbmc z3"
    assert properties == {"<all>": "UNKNOWN"}, f"props: {properties}"
    assert cex == []
