"""LogicPilot hardware flow internals."""
from __future__ import annotations


import re

from .variables import build_vars

# Match only log lines where a tool reports it actually inferred a latch from
# the *design*, not lines that merely mention the word "latch". The earlier
# pattern (\$_?DLATCH | \bLATCH\b, case-insensitive) produced false positives on
# every ice40 run because:
#   - yosys names a pass "Executing PROC_DLATCH pass" regardless of the design,
#   - yosys loads its ice40 standard-cell library, which defines modules
#     `$_DLATCH_N_` / `$_DLATCH_P_`,
#   - the same `$_DLATCH_P_` library module is then optimized, printing it
#     dozens more times.
# None of those imply a latch in the user's RTL. A genuine inference instead
# prints an explicit message naming the signal/process, e.g. yosys:
#   "Latch inferred for signal `\foo.\q' from process ..."
# or vendor wording "inferred latch for ...". We match those, plus a real
# instantiated $_DLATCH_/$dlatch *cell* (one preceded by "cell"/"created"),
# never a bare type name from a library definition.
QUALITY_RED_FLAGS = {
    "inferred_latch": (
        r"latch inferred for|inferred latch for|"
        r"\binferred\s+latch(?:es)?\b|"
        r"(?:created|cell|adding)[^\n]*\$_?[dD][lL]atch|"
        # a stat line counting instantiated latch cells, e.g. "$_DLATCH_P_  2"
        # or "SB_DFFL 3" — a cell type followed by a positive integer count.
        r"^\s*\$?_?[dD][lL]atch\w*\s+[1-9]\d*\s*$"
    ),
    # multiple drivers on one net — a real elaboration bug
    "multi_driver": r"multiple drivers|multi-driver|driven by more than one|conflicting drivers",
}

# yosys reads its target library (e.g. ice40 latches_map.v) during synthesis and
# echoes every module it defines/optimizes, including `$_DLATCH_P_`. Strip those
# library-load/optimize sections before scanning so library cell names can never
# be mistaken for a latch in the user's design.
_LIBRARY_NOISE = re.compile(
    r"^.*(?:latches_map\.v|cells_map\.v|cells_sim\.v|"
    r"(?:module|Optimizing module|cells in module|cells of type)\s+`?\\?\$_[A-Z])"
    r".*$",
    re.MULTILINE,
)


def _strip_library_noise(log_text: str) -> str:
    return _LIBRARY_NOISE.sub("", log_text)


def quality_warnings(log_text: str) -> list[str]:
    """Scan a stage log for synthesis red flags worth elevating to warnings."""
    out: list[str] = []
    scan_text = _strip_library_noise(log_text)
    if re.search(QUALITY_RED_FLAGS["inferred_latch"], scan_text, re.IGNORECASE | re.MULTILINE):
        out.append("inferred latch detected — usually an incomplete if/case "
                    "(missing else/default) or missing assignment; fix in RTL")
    if re.search(QUALITY_RED_FLAGS["multi_driver"], scan_text, re.IGNORECASE):
        out.append("multiple drivers on a net detected — likely an elaboration bug")
    return out

def power_warnings(log_text: str, metrics: dict, cfg: dict) -> list[str]:
    """Warnings specific to power estimation/reporting."""
    out: list[str] = []
    has_power = any(k.endswith("_power_w") or k in {"total_power_w", "static_power_w", "dynamic_power_w"} for k in metrics)
    if not has_power:
        out.append("no power metrics parsed; inspect the raw power report/log or add [metrics.patterns] overrides")

    # Vendor reports often disclose that no activity was annotated and vectorless
    # defaults were used. That is valid for early exploration but not enough for
    # power-budget signoff.
    if re.search(r"vectorless|default\s+(?:switching|toggle)|no\s+(?:activity|saif|vcd)|not\s+annotated|unannotated", log_text, re.I):
        out.append("power uses vectorless/default switching activity; provide SAIF/VCD from representative simulation for actionable numbers")

    budget = cfg.get("power", {}).get("total_budget_w")
    total = metrics.get("total_power_w")
    try:
        if budget is not None and isinstance(total, (int, float)) and total > float(budget):
            out.append(f"total power {total} W exceeds budget {float(budget)} W")
    except (TypeError, ValueError):
        pass
    return out

# Power activity-source enum (closed contract — agents may rely on these
# exact strings). Adding new values requires a CHANGELOG note + a JSON-
# CONTRACT.md update. Order is documentation-only; consumers don't index.
POWER_ACTIVITY_SOURCES = (
    "saif-annotated",      # SAIF read by the power tool (highest fidelity)
    "vcd-annotated",       # VCD read directly (no SAIF intermediary)
    "vectorless-default",  # tool fell back to default switching rates
    "manual-override",     # user supplied [activity].toggle_rate
    "unknown",             # nothing in log/config we recognize
)


def power_assumptions(log_text: str, cfg: dict, variables: dict | None = None) -> dict:
    """Summarize the assumptions that make a power number meaningful.

    `variables` may be passed in by callers that already computed build_vars(cfg)
    so the work is not repeated; it is computed here when omitted.

    ``activity_source`` is one of ``POWER_ACTIVITY_SOURCES`` — a closed
    enum so agents and downstream CI can dispatch on it deterministically.
    """
    if variables is None:
        variables = build_vars(cfg)
    saif = variables.get("saif_file", "")
    vcd = variables.get("vcd_file", "")
    activity_cfg = cfg.get("activity", {}) if isinstance(cfg.get("activity"), dict) else {}
    activity = variables.get("activity_file", "") or saif or vcd
    manual_toggle = activity_cfg.get("toggle_rate")

    # Precedence: explicit annotated file > log evidence > manual toggle
    # > vectorless default > unknown. SAIF beats VCD because SAIF is the
    # processed/decayed form a power tool actually consumes.
    if saif:
        source = "saif-annotated"
    elif vcd:
        source = "vcd-annotated"
    elif re.search(r"SAIF", log_text, re.I):
        source = "saif-annotated"
    elif re.search(r"VCD", log_text, re.I):
        source = "vcd-annotated"
    elif manual_toggle is not None:
        source = "manual-override"
    elif re.search(r"vectorless|default\s+(?:switching|toggle)|no\s+(?:activity|saif|vcd)|not\s+annotated|unannotated", log_text, re.I):
        source = "vectorless-default"
    else:
        source = "unknown"

    power_cfg = cfg.get("power", {})
    high_fidelity_sources = {"saif-annotated", "vcd-annotated"}
    return {
        "activity_source": source,
        "activity_file": activity or None,
        "activity_instance": variables.get("activity_instance") or None,
        "clock_mhz": str(cfg.get("project", {}).get("clock_mhz", "")) or None,
        "voltage": power_cfg.get("voltage"),
        "temperature_c": power_cfg.get("temperature_c"),
        "total_budget_w": power_cfg.get("total_budget_w"),
        "toggle_rate": activity_cfg.get("toggle_rate"),
        "confidence": "high" if source in high_fidelity_sources else "early_estimate",
    }

# v0.7b project marker for seed logging. Testbenches must print exactly
# this line once at simulation start so the driver can verify
# reproducibility without trying to regex-guess vendor-specific formats.
# See hardware-verification skill for the convention.
LOGICPILOT_SEED_MARKER_RE = re.compile(r"LOGICPILOT_SEED=\d+")
URANDOM_USE_RE = re.compile(r"\$urandom|\brandomize\s*\(|\brandc?\b", re.I)
# Patterns that prove the testbench actually executed a print task.
# v0.7b used to look for the literal `$display` token, but open-source
# sims (iverilog, verilator) print only the resolved output — the
# token never appears in the log. So the regex needs to match both:
#  - the literal token (vendor tools that echo "$display(...) at time …")
#  - the *evidence* the token ran: LOGICPILOT_SEED marker, PASS/FAIL
#    markers, UVM tag prefixes which DO echo their own name.
OBSERVABLE_OUTPUT_RE = re.compile(
    r"\$display|\$monitor|\$write"
    r"|UVM_INFO|UVM_WARNING|UVM_ERROR|UVM_FATAL"
    r"|LOGICPILOT_SEED=\d+"
    r"|\b(?:PASS|FAIL|TEST_PASS|TEST_FAIL|SUCCESS)\b",
    re.I,
)


def verification_warnings(log_text: str, metrics: dict, cfg: dict) -> list[str]:
    """Warnings specific to simulation, coverage, and regression reporting.

    v0.7b additions (§4b.2): three heuristic checks for 'looks-like-an-
    empty-test' simulations. All are warnings (not fails) — they fire on
    legitimate but suspicious patterns; the user keeps full control."""
    out: list[str] = []
    verification_cfg = cfg.get("verification", {})

    # Coverage goal check (pre-existing).
    coverage_goal = verification_cfg.get("coverage_goal_pct")
    cov_keys = [k for k in metrics if k.endswith("_coverage_pct")]
    if coverage_goal is not None:
        try:
            goal = float(coverage_goal)
            for k in cov_keys:
                v = metrics.get(k)
                if isinstance(v, (int, float)) and v < goal:
                    out.append(f"{k}={v}% is below coverage_goal_pct={goal}%")
        except (TypeError, ValueError):
            pass

    # v0.7b §4b.2 #1: no observable activity in the log.
    # A TB that compiles + runs but produces zero $display / UVM_INFO is
    # almost certainly not exercising the DUT. False positive: tests
    # that only check exit code without printing.
    if log_text and not OBSERVABLE_OUTPUT_RE.search(log_text):
        out.append(
            "testbench produced no observable activity ($display / $monitor "
            "/ UVM_INFO etc.); check self-checking discipline (see "
            "hardware-verification skill)"
        )

    # v0.7b §4b.2 #2: randomized test without the LOGICPILOT_SEED marker.
    # Replaces the v0.6 regex-guess (\bseed\b|sv_seed|...) with the
    # project-level convention — testbench prints
    # `$display("LOGICPILOT_SEED=%0d", seed);` exactly once.
    if URANDOM_USE_RE.search(log_text) and not LOGICPILOT_SEED_MARKER_RE.search(log_text):
        out.append(
            "random test without LOGICPILOT_SEED marker; run is not "
            "reproducible — add `$display(\"LOGICPILOT_SEED=%0d\", seed);` "
            "at simulation start (see hardware-verification skill)"
        )

    if cov_keys and re.search(r"\b(FAIL|FATAL|ERROR|mismatch)\b", log_text, re.I):
        out.append("coverage appears in a failing log; do not merge coverage from failed tests")
    return out


def verification_failures(log_text: str, metrics: dict, cfg: dict) -> list[str]:
    """Hard-fail conditions for sim/verify/coverage stages.

    v0.7b §4b.3 — require_seed_log opt-in gate.
    v0.9 §6.4   — coverage_enforcement = "fail" upgrades below-goal
                  coverage from warning to hard fail.

    Both are opt-in. Default behaviour (keys absent) keeps the failure
    list empty so existing projects don't suddenly turn red.
    """
    out: list[str] = []
    verification_cfg = cfg.get("verification", {})

    # v0.7b: require_seed_log
    if (
        verification_cfg.get("require_seed_log")
        and URANDOM_USE_RE.search(log_text)
        and not LOGICPILOT_SEED_MARKER_RE.search(log_text)
    ):
        out.append(
            "[verification].require_seed_log = true: randomized test has no "
            "LOGICPILOT_SEED marker — required for reproducibility. Add "
            "`$display(\"LOGICPILOT_SEED=%0d\", seed);` to the testbench start."
        )

    # v0.9: coverage_enforcement = "fail" turns below-goal coverage into a
    # hard fail. Accepted values: "fail" / "warn" / "off". Default is
    # "warn" (matches v0.8 behaviour); flow.toml can set "fail" for
    # stricter CI. v1.x may flip the default.
    enforcement = str(verification_cfg.get("coverage_enforcement", "warn")).lower()
    if enforcement == "fail":
        coverage_goal = verification_cfg.get("coverage_goal_pct")
        if coverage_goal is not None:
            try:
                goal = float(coverage_goal)
                for k, v in metrics.items():
                    if (
                        k.endswith("_coverage_pct")
                        and isinstance(v, (int, float))
                        and v < goal
                    ):
                        out.append(
                            f"[verification].coverage_enforcement='fail': "
                            f"{k}={v}% is below coverage_goal_pct={goal}%"
                        )
            except (TypeError, ValueError):
                pass
    return out


def sim_walltime_warnings(
    elapsed_s: float | None,
    metrics: dict,
    log_text: str | None = None,
) -> list[str]:
    """Heuristic: did the sim actually run anything? (v0.7b §4b.2 #3)

    Fires when wall-clock < 100 ms AND we can't find evidence of cycles
    in the metrics. ``log_text`` is optional but recommended — when the
    LOGICPILOT_SEED marker appears in the log, the TB definitely ran a
    print task and the heuristic suppresses to avoid false positives
    on fast open-source simulators (verilator's no-trace builds finish
    a small TB in tens of ms).
    """
    out: list[str] = []
    if elapsed_s is None or elapsed_s >= 0.1:
        return out

    # Try to corroborate with cycle count if a metrics parser captured one.
    cycles = metrics.get("cycles") or metrics.get("sim_cycles")
    if cycles is not None and isinstance(cycles, (int, float)) and cycles >= 100:
        return out

    # If the LOGICPILOT_SEED marker appears in the log, the TB printed
    # something — sim ran, just fast. Suppress the warning.
    if log_text and LOGICPILOT_SEED_MARKER_RE.search(log_text):
        return out

    out.append(
        f"testbench finished suspiciously fast (wall-clock {elapsed_s*1000:.0f} ms"
        + (f", {cycles} cycles" if cycles is not None else ", no cycle count parsed")
        + "); verify the DUT actually got exercised"
    )
    return out
