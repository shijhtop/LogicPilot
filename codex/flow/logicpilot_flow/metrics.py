"""LogicPilot hardware flow internals."""
from __future__ import annotations


import re

# Shared number capture: at least one digit, optional fractional part,
# optional leading minus. The earlier `(-?[\d.]+)` accepted bare `.`
# (e.g. captured the trailing dot in "Dynamic Voltage Scaling: not
# enabled." as `dynamic_power_w: '.'`).
_NUM = r"(-?\d+(?:\.\d+)?)"
# Coverage / fmax label-to-number gap: forbid letters so prose like
# "Coverage estimated for 12 testcases at 95.2%" doesn't capture `12`
# as the metric value.
_NO_LETTERS = r"[^\n\dA-Za-z-]*?"

DEFAULT_METRIC_PATTERNS = {
    # yosys "stat" cell rows + vendor utilization-report rows
    "luts": r"(?:Number of LUTs|SB_LUT4|CLB LUTs|Slice LUTs|Total LUTs|ALMs? used)[ \t:|]+(\d[\d,]*)",
    "ffs": r"(?:SB_DFF\w*|CLB Registers|Slice Registers|Total registers|Number of FFs)[ \t:|]+(\d[\d,]*)",
    "bram": r"(?:SB_RAM\w*|Block RAM Tile|RAMB\w+|M9K|M10K|M20K)[ \t:|]+(\d[\d,]*)",
    "dsp": r"(?:SB_MAC16|DSP48\w*|DSP Blocks?|DSPs)[ \t:|]+(\d[\d,]*)",
    # nextpnr "Max frequency", Vivado/Quartus Fmax (number on same line)
    "fmax_mhz": rf"(?:Max frequency for clock[^:\n]*:|Restricted Fmax[^:\n]*:|Fmax[^:\n]*:)[ \t]*{_NUM}[ \t]*MHz",
    # Worst negative slack (timing). Negative => failing. `\bWNS\b` so
    # "WNS-related" / "WNSpath" don't false-match.
    "wns_ns": rf"(?:Worst Negative Slack|\bWNS\b)[^\n\d-]*?{_NUM}",

    # Verification/coverage report metrics. Gap forbids letters so
    # narrative text between the label and a stray number ("estimated
    # for 12 testcases") doesn't slip through as the coverage value.
    "functional_coverage_pct": rf"(?:Functional Coverage|Functional coverage|covergroup coverage){_NO_LETTERS}{_NUM}\s*%",
    "code_coverage_pct": rf"(?:Code Coverage|Code coverage|overall code coverage){_NO_LETTERS}{_NUM}\s*%",
    "line_coverage_pct": rf"(?:Line Coverage|Statement Coverage|line coverage){_NO_LETTERS}{_NUM}\s*%",
    "branch_coverage_pct": rf"(?:Branch Coverage|branch coverage){_NO_LETTERS}{_NUM}\s*%",
    "toggle_coverage_pct": rf"(?:Toggle Coverage|toggle coverage){_NO_LETTERS}{_NUM}\s*%",
    "fsm_coverage_pct": rf"(?:FSM Coverage|state coverage|fsm coverage){_NO_LETTERS}{_NUM}\s*%",
    "assertion_coverage_pct": rf"(?:Assertion Coverage|assertion coverage|SVA coverage){_NO_LETTERS}{_NUM}\s*%",

}

# Power / thermal metrics — kept SEPARATE from DEFAULT_METRIC_PATTERNS
# because their labels (Static, Signal, Clock, Logic, BRAM, DSP) are
# bare English words that match all over synthesis logs. parse_metrics
# only applies these when the stage spec opts in (stage name matches
# POWER_STAGE_NAMES) so a yosys synth run no longer surfaces
# fictional `static_power_w: 8.0` numbers. Vivado uses headers like
# "| Device Static (W) | 0.334 |"; Quartus uses
# "Total Thermal Power Dissipation: 123.4 mW".
POWER_STAGE_NAMES: frozenset[str] = frozenset({"power"})

# Bare-word alternative for table-column or label-colon context only:
# `WORD` (optionally with a parenthesised unit hint like "(W)") followed
# by whitespace + `|` (Vivado / text table) or `:` (Quartus label).
# Plain prose like "Clock Network: 24" doesn't match because `Network`
# intervenes before any `|` or `:`. Vivado headlines use bare `Dynamic`
# / `Static` with a `(W)` unit hint, so the `(W)` allowance is required.
def _bare(word: str) -> str:
    return rf"\b{word}\b(?:\s*\([^)]*\))?\s*[|:]"

POWER_METRIC_PATTERNS = {
    "total_power_w": rf"(?:Total On-Chip Power|Total Thermal Power Dissipation|Total Power|Chip Power)[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "dynamic_power_w": rf"(?:Total Dynamic Power|Dynamic Power|{_bare('Dynamic')})[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "static_power_w": rf"(?:Device Static|Static Power|Leakage Power|{_bare('Static')})[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "clock_power_w": rf"(?:Clock Power|{_bare('Clocks?')})[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "signal_power_w": rf"(?:Signal Power|{_bare('Signals?')})[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "logic_power_w": rf"(?:Logic Power|{_bare('Logic')})[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "bram_power_w": rf"(?:BRAM Power|Block RAM|{_bare('BRAM')})[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "dsp_power_w": rf"(?:DSP Power|{_bare('DSPs?')}|{_bare('Multiplier')})[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "io_power_w": rf"(?:I/O Power|IO Power|{_bare('I/O')}|{_bare('IO')})[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "power_budget_w": rf"(?:Design Power Budget|Power Budget)[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "power_margin_w": rf"(?:Power Budget Margin|Power Margin)[^\n\d-]*?{_NUM}\s*(mW|uW|nW|W)?",
    "junction_temp_c": rf"(?:Junction Temperature|\bTj\b)[^\n\d-]*?{_NUM}",
    "thermal_margin_c": rf"(?:Thermal Margin)[^\n\d-]*?{_NUM}",
}

def _coerce_metric_value(key: str, raw: str, unit: str | None = None):
    cleaned = str(raw).replace(",", "")
    try:
        value = float(cleaned) if "." in cleaned else int(cleaned)
    except ValueError:
        return raw

    if key.endswith("_w") and unit:
        scale = {
            "kw": 1000.0,
            "w": 1.0,
            "mw": 1e-3,
            "uw": 1e-6,
            "µw": 1e-6,
            "nw": 1e-9,
        }.get(unit.lower())
        if scale is not None:
            value = float(value) * scale
    return value

def parse_metrics(log_text: str, cfg: dict, stage_name: str | None = None) -> dict:
    """Extract numeric metrics from a stage log.

    ``stage_name`` opts the per-stage power patterns in. When the
    stage is one of POWER_STAGE_NAMES (``power``) we
    also run the bare-word power regexes which would otherwise create
    false positives on synth / pnr logs. Project-defined power-style
    stages can opt in via ``[metrics.power_stages] = ["my_power"]``.
    Default ``None`` keeps the call site working unchanged — and is
    safe, since the bare-word patterns stay disabled.
    """
    patterns = dict(DEFAULT_METRIC_PATTERNS)

    metrics_cfg = cfg.get("metrics", {}) if isinstance(cfg.get("metrics"), dict) else {}
    extra_power_stages = {
        str(s) for s in metrics_cfg.get("power_stages", []) if isinstance(s, str)
    }
    if stage_name and (stage_name in POWER_STAGE_NAMES or stage_name in extra_power_stages):
        patterns.update(POWER_METRIC_PATTERNS)

    # Project overrides apply last so they can shadow either set.
    patterns.update(metrics_cfg.get("patterns", {}))

    found: dict = {}
    for key, pat in patterns.items():
        m = re.search(pat, log_text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            unit = None
            if m.lastindex and m.lastindex >= 2:
                unit = m.group(2)
            found[key] = _coerce_metric_value(key, raw, unit)
    return found

def evaluate_checks(log_text: str, checks: dict | None) -> dict:
    """Evaluate optional machine-readable pass/fail markers.

    Useful for simulators that exit 0 even when a self-checking testbench printed
    FAIL, or for regression policy where a PASS marker is required.
    """
    checks = checks or {}
    if not checks:
        return {}
    pass_regex = checks.get("pass_regex")
    fail_regex = checks.get("fail_regex")
    require_pass = bool(checks.get("require_pass", False))

    fail_seen = bool(fail_regex and re.search(str(fail_regex), log_text, re.IGNORECASE | re.MULTILINE))
    pass_seen = bool(pass_regex and re.search(str(pass_regex), log_text, re.IGNORECASE | re.MULTILINE))
    status = "pass"
    reasons: list[str] = []
    if fail_seen:
        status = "fail"
        reasons.append("fail_regex matched")
    if require_pass and pass_regex and not pass_seen:
        status = "fail"
        reasons.append("required pass_regex not seen")
    return {
        "status": status,
        "pass_seen": pass_seen,
        "fail_seen": fail_seen,
        "require_pass": require_pass,
        "reasons": reasons,
    }
