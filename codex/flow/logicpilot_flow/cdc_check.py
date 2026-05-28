"""Built-in cdc-check stage (v0.8 §5, R7/R8 added in v1.0+ via Verible AST).

Validates a CDC inventory file (default ``docs/cdc-inventory.json``,
conforming to ``docs/schemas/cdc-inventory.schema.json``) against the
hardware-cdc skill's safety rules. The inventory itself is produced by
the ``rtl-cdc-reviewer`` sub-agent (Claude Code) or by the equivalent
Codex prompt ``/lp-cdc-review``.

Rules implemented:

- **Truth table** (R1-R3 combined): ``payload_kind × synchronizer``
  membership. Disallowed combinations fail.
- **R4**: ``verdict: "unsafe"`` requires non-empty ``rationale``.
- **R5**: ``verdict: "waived"`` requires non-empty ``rationale`` AND
  ``evidence`` (with ``file`` + ``line``).
- **R6**: ``set_clock_groups_declared: false`` with any crossings → fail.
- **Special "none" rule** (C4): ``synchronizer: "none"`` always implies
  unsafe — must pair with ``verdict: "waived"`` or ``verdict: "unsafe"``.
- **Conditional schema** (mirrors the ``allOf`` block in
  ``cdc-inventory.schema.json``): ``from_clock`` must differ from
  ``to_clock`` (a same-clock entry isn't a crossing); ``synchronizer in
  {2ff, 3ff, mux_synchronizer}`` requires an integer ``stages >= 2``;
  ``synchronizer == handshake_req_ack`` requires an integer
  ``cycles_to_settle >= 1``. Skipped for ``verdict == waived`` rows,
  same as the truth-table check.
- **R7** (``--experimental-ast`` + Verible on PATH): walk the RTL
  AST and enumerate signals whose LHS clocked drivers span more than
  one clock domain (i.e. a signal is written in ``always @(posedge
  clkA)`` AND ``always @(posedge clkB)``), then FAIL when such a
  multi-driven leaf isn't covered by an inventory crossing. This is a
  **narrow** heuristic: it catches accidental multi-clock writes and
  dual-port memory writes from two domains, but NOT the more common
  "drive in one clock, read+synchronize in another" CDC — that needs
  RHS-read traversal and is deferred to a future round.
- **R8** (same dep): WARN when an inventory crossing references a
  signal that AST enumeration can't find any clocked driver for —
  likely a stale inventory row.

Engine disclosure: every JSON envelope includes ``audit_engine``
(``"regex"`` or ``"verible-ast"``). The AST path is opt-in (flag) and
silently degrades to regex when the binary isn't installed; in that
case ``audit_engine`` stays ``"regex"`` and a warning row in the
top-level envelope (from features.py) tells the user the flag had no
effect. This is the v1 contract — agents may rely on the field always
being present.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import _expand_globs


# When R7 fails we still want the user to be able to see WHICH crossings
# were enumerated. We cap at this many rows in `enumerated_drivers` so
# huge designs don't blow up the JSON envelope.
_MAX_ENUMERATED_DRIVERS_IN_JSON = 200


# Truth table: payload_kind → allowed synchronizers.
# Anything not in the allowed set, including "none", is a rule violation
# (subject to verdict overrides per R5 waived path).
TRUTH_TABLE: dict[str, set[str]] = {
    "pulse":         {"handshake_req_ack", "async_fifo", "waived"},
    "level":         {"2ff", "3ff", "handshake_req_ack", "mux_synchronizer",
                      "waived",
                      # over-engineering but tolerated — verdict carries it
                      "gray_counter", "async_fifo"},
    "bus":           {"async_fifo", "gray_counter", "handshake_req_ack", "waived"},
    "reset_release": {"2ff", "3ff", "handshake_req_ack", "waived"},
}

# Required top-level fields per the schema. Soft-validated here so the
# stage doesn't require jsonschema as a runtime dep (zero-deps promise).
REQUIRED_TOP_KEYS = (
    "version", "generated_by", "generated_at",
    "top_module", "clocks", "crossings",
    "set_clock_groups_declared",
)

REQUIRED_CROSSING_KEYS = (
    "from_clock", "to_clock", "signal",
    "payload_kind", "synchronizer", "verdict",
)

# Synchronizers that require a numeric `stages` field per the schema's
# allOf block. mux_synchronizer is included because the destination side
# is a 2FF/3FF flop chain that needs the same MTBF accounting.
_SYNCS_REQUIRING_STAGES = ("2ff", "3ff", "mux_synchronizer")


def _default_inventory_path(cfg: dict) -> Path:
    """Default location: docs/cdc-inventory.json under the project root."""
    cdc_cfg = cfg.get("cdc", {}) if isinstance(cfg.get("cdc"), dict) else {}
    rel = str(cdc_cfg.get("inventory", "docs/cdc-inventory.json"))
    root: Path = cfg["_root"]
    return root / rel


def _add(findings: list[dict], severity: str, rule: str,
         crossing_idx: int | None, message: str) -> None:
    """Append a finding row. crossing_idx=None for top-level issues."""
    row: dict[str, Any] = {"severity": severity, "rule": rule, "message": message}
    if crossing_idx is not None:
        row["crossing_index"] = crossing_idx
    findings.append(row)


def _check_top_shape(inv: dict, findings: list[dict]) -> bool:
    """Verify required top-level keys + basic types. Returns False if
    the inventory is too broken to rule-check."""
    ok = True
    for key in REQUIRED_TOP_KEYS:
        if key not in inv:
            _add(findings, "high", "cdc_missing_top_key", None,
                 f"inventory missing required top-level key '{key}'")
            ok = False
    # Bail early if the structural skeleton is broken.
    if not ok:
        return False
    if not isinstance(inv.get("crossings"), list):
        _add(findings, "high", "cdc_crossings_not_array", None,
             "'crossings' must be a JSON array")
        return False
    if not isinstance(inv.get("set_clock_groups_declared"), bool):
        _add(findings, "high", "cdc_clock_groups_bad_type", None,
             "'set_clock_groups_declared' must be a boolean")
        return False
    if inv.get("version") != "1":
        _add(findings, "medium", "cdc_unsupported_version", None,
             f"schema version '{inv.get('version')}' not recognised; expected '1'")
    return True


def _check_truth_table(idx: int, x: dict, findings: list[dict]) -> None:
    """R1-R3 combined as a single truth-table lookup, plus the C4 'none'
    special rule."""
    payload = x.get("payload_kind")
    sync = x.get("synchronizer")
    verdict = x.get("verdict")

    if payload not in TRUTH_TABLE:
        _add(findings, "high", "cdc_unknown_payload_kind", idx,
             f"unknown payload_kind '{payload}'; expected one of "
             f"{sorted(TRUTH_TABLE.keys())}")
        return

    # Special rule: synchronizer="none" always implies unsafe.
    if sync == "none" and verdict != "waived":
        _add(findings, "high", "cdc_unprotected_crossing", idx,
             f"synchronizer='none' requires verdict='waived' with rationale "
             f"+ evidence; got verdict='{verdict}'")
        return

    # waived verdict short-circuits the truth table (R5 already validated
    # rationale + evidence elsewhere).
    if verdict == "waived":
        return

    allowed = TRUTH_TABLE[payload]
    if sync not in allowed:
        _add(findings, "high", "cdc_truth_table_violation", idx,
             f"payload_kind='{payload}' × synchronizer='{sync}' is not in "
             f"the truth table (allowed: {sorted(allowed - {'waived'})}); "
             f"either change the synchronizer or set verdict='waived' with "
             f"rationale + evidence")


def _check_verdict_required_fields(idx: int, x: dict, findings: list[dict]) -> None:
    """R4 (unsafe→rationale) and R5 (waived→rationale + evidence)."""
    verdict = x.get("verdict")

    if verdict == "unsafe":
        if not (x.get("rationale") or "").strip():
            _add(findings, "high", "cdc_unsafe_missing_rationale", idx,
                 "verdict='unsafe' requires non-empty 'rationale' explaining the hazard")

    if verdict == "waived":
        if not (x.get("rationale") or "").strip():
            _add(findings, "high", "cdc_waived_missing_rationale", idx,
                 "verdict='waived' requires non-empty 'rationale' justifying the waiver")
        evidence = x.get("evidence") or {}
        if not (evidence.get("file") and evidence.get("line")):
            _add(findings, "high", "cdc_waived_missing_evidence", idx,
                 "verdict='waived' requires 'evidence' with 'file' + 'line'")


def _check_conditional_fields(idx: int, x: dict, findings: list[dict]) -> None:
    """Per-crossing conditional schema validation (mirrors schema's allOf).

    Runtime parallel to ``cdc-inventory.schema.json``'s ``allOf`` block.
    Skipped for ``verdict == waived`` rows — a waiver consciously
    accepts an incomplete spec, same as the truth-table check.
    """
    if x.get("verdict") == "waived":
        return

    from_clk = x.get("from_clock")
    to_clk = x.get("to_clock")
    if (
        isinstance(from_clk, str) and isinstance(to_clk, str)
        and from_clk and to_clk and from_clk == to_clk
    ):
        _add(findings, "high", "cdc_same_clock_not_crossing", idx,
             f"from_clock and to_clock are both '{from_clk}'; same-domain "
             "registers are not CDC and should not be in this inventory")

    sync = x.get("synchronizer")
    if sync in _SYNCS_REQUIRING_STAGES:
        stages = x.get("stages")
        if not isinstance(stages, int) or isinstance(stages, bool) or stages < 2:
            _add(findings, "high", "cdc_missing_stages", idx,
                 f"synchronizer='{sync}' requires integer 'stages' >= 2 for "
                 f"MTBF accounting; got {stages!r}")

    if sync == "handshake_req_ack":
        cts = x.get("cycles_to_settle")
        if not isinstance(cts, int) or isinstance(cts, bool) or cts < 1:
            _add(findings, "high", "cdc_missing_cycles_to_settle", idx,
                 f"synchronizer='handshake_req_ack' requires integer "
                 f"'cycles_to_settle' >= 1 (round-trip cycles before next "
                 f"request); got {cts!r}")


def _check_crossing_shape(idx: int, x: dict, findings: list[dict]) -> bool:
    """Verify per-crossing required keys. Returns False if the crossing
    is too broken to rule-check."""
    if not isinstance(x, dict):
        _add(findings, "high", "cdc_crossing_not_object", idx,
             f"crossing #{idx} must be a JSON object")
        return False
    missing = [k for k in REQUIRED_CROSSING_KEYS if k not in x]
    if missing:
        _add(findings, "high", "cdc_crossing_missing_keys", idx,
             f"crossing #{idx} missing required keys: {missing}")
        return False
    return True


# --- R7 / R8: AST-based driver enumeration --------------------------------

def _iter_rtl_sources(cfg: dict) -> list[Path]:
    """Resolve the project's RTL source globs to absolute Verilog/SV files.

    Mirrors ``audit._iter_audit_source_files`` but inlined to avoid
    circular import. VHDL files are ignored — Verible only parses
    Verilog / SystemVerilog.
    """
    root: Path = cfg["_root"]
    proj = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    patterns = proj.get("src_ordered", proj.get("src", []))
    files = []
    for f in _expand_globs(patterns, root):
        p = Path(f)
        if not p.is_absolute():
            p = root / p
        if p.exists() and p.suffix.lower() in {".v", ".vh", ".sv", ".svh"}:
            files.append(p.resolve())
    seen, out = set(), []
    for p in files:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def _signal_leaf(signal: str) -> str:
    """Reduce a hierarchical inventory signal to its leaf identifier.

    Inventory writes hierarchical paths relative to ``top_module`` —
    e.g. ``u_fifo.wr_ptr_gray``. The AST walker yields bare identifiers
    (``wr_ptr_gray``) since it doesn't reason about instance trees.
    We match on the leaf to bridge the two views. This is intentionally
    permissive: two crossings with the same leaf in different instances
    collapse to one driver entry, which is acceptable for R7/R8
    coverage rather than precision.
    """
    return signal.rsplit(".", 1)[-1]


def _enumerate_drivers(cfg: dict) -> tuple[list[dict], list[Path]]:
    """Run Verible over every RTL source file; return ``(drivers, parsed_files)``.

    Each driver row: ``{"clock": str, "signal": str, "file": str, "line": int}``.
    ``parsed_files`` is the list of files Verible accepted (return value of
    ``parse_file`` was non-None).

    Best-effort: files Verible refuses to parse are silently skipped so a
    syntax error in one module doesn't kill the whole CDC pass.
    """
    # Local import keeps cdc_check importable on machines without
    # verible — the verible_client module itself is stdlib-only, but
    # this is the right boundary to apply lazy-load discipline.
    from . import verible_client

    if not verible_client.ast_available():
        return [], []

    root: Path = cfg["_root"]
    drivers: list[dict] = []
    parsed: list[Path] = []
    for src in _iter_rtl_sources(cfg):
        ast = verible_client.parse_file(src)
        if not ast:
            continue
        parsed.append(src)
        try:
            rel = str(src.relative_to(root))
        except ValueError:
            rel = str(src)
        for clock, signal, line in verible_client.iter_clocked_drivers(ast):
            drivers.append({
                "clock": clock,
                "signal": signal,
                "file": rel,
                "line": line,
            })
    return drivers, parsed


def _check_r7_r8(
    inv: dict,
    drivers: list[dict],
    findings: list[dict],
) -> dict:
    """Apply R7 (missing-from-inventory) and R8 (stale-inventory) rules.

    Returns a small disclosure summary the caller folds into the JSON
    envelope: ``{enumerated_count, signals_in_rtl, signals_in_inventory}``.

    Matching rule (intentionally loose):
      - Two drivers in the same clock domain that also drive the same
        leaf signal collapse to one logical driver.
      - An inventory crossing is "covered" by a driver iff
        ``crossing.signal`` leaf matches the driver's signal AND
        ``crossing.from_clock`` matches the driver's clock.
      - R7 (fail): a driver exists in some clock domain whose
        (from_clock, signal-leaf) pair is NOT in any inventory row.
        Only flag pairs where another driver in a DIFFERENT clock
        domain also touches the same leaf — i.e. evidence of an
        actual CDC, not just a normal flop.
      - R8 (warn): an inventory crossing whose (from_clock, leaf) pair
        has no AST driver to back it.
    """
    crossings = inv.get("crossings", [])

    # Build leaf → {clocks that drive it}.
    leaf_clocks: dict[str, set[str]] = {}
    leaf_first_line: dict[str, int] = {}
    for d in drivers:
        leaf_clocks.setdefault(d["signal"], set()).add(d["clock"])
        leaf_first_line.setdefault(d["signal"], d.get("line") or 0)

    # Apparent CDC leaves: signals driven (LHS) in 2+ clock domains.
    #
    # NOTE — this is a *narrow* heuristic. It catches:
    #   - signals that have multiple assignment sites in different
    #     `always @(posedge X)` blocks (e.g. accidental multi-clock
    #     writes, dual-port memory writes from two domains).
    #
    # It does NOT catch the most common CDC shape — a signal driven in
    # one domain and READ by a sample / synchronizer in another — because
    # we only enumerate LHS clocked drivers, not RHS reads. A true
    # "missing-inventory" detector would need to walk RHS expressions in
    # every clocked block and resolve their source clocks. That's a
    # larger AST traversal deferred to a future round; until then this
    # rule is a multi-driver-cross-domain check, not a full CDC scanner,
    # and the doc string reflects that.
    apparent_cdc_leaves: set[str] = {
        leaf for leaf, clocks in leaf_clocks.items() if len(clocks) >= 2
    }

    # Inventory coverage: just the set of signal leaves mentioned anywhere
    # in the inventory (regardless of which from_clock). The truth-table
    # and verdict checks above already validate per-row payload/sync
    # combinations; R7's job is only to catch crossings the inventory
    # forgot to mention at all.
    inventory_leaves: set[str] = set()
    for x in crossings:
        if not isinstance(x, dict):
            continue
        sig = x.get("signal")
        if isinstance(sig, str):
            inventory_leaves.add(_signal_leaf(sig))

    # R7: apparent CDC leaves not covered by ANY inventory row.
    missing_leaves = sorted(apparent_cdc_leaves - inventory_leaves)
    for leaf in missing_leaves:
        line = leaf_first_line.get(leaf, 0)
        clocks = sorted(leaf_clocks.get(leaf, set()))
        _add(findings, "high", "cdc_driver_missing_from_inventory", None,
             f"AST sees signal '{leaf}' driven across clock domains "
             f"{clocks} (line ~{line}); no inventory row mentions this "
             "signal. Add the crossing to docs/cdc-inventory.json with "
             "the correct payload_kind/synchronizer or mark it waived.")

    # R8: inventory leaves the AST can't find a driver for at all.
    # A signal driven by exactly one domain may still be a legitimate
    # CDC source (the sync flop on the destination side is what shows
    # up in the second domain — and that flop's *output* gets a
    # different name); only warn when AST sees NO driver for the leaf.
    truly_stale = sorted(inventory_leaves - set(leaf_clocks.keys()))
    for leaf in truly_stale:
        _add(findings, "medium", "cdc_inventory_signal_not_in_rtl", None,
             f"inventory crossing for signal leaf '{leaf}' has no "
             "matching clocked driver in the RTL AST. Either the "
             "signal was renamed/removed (delete the inventory row) "
             "or AST enumeration missed it (file a bug + waive the row).")

    return {
        "enumerated_count": len(drivers),
        "apparent_cdc_pairs": len(apparent_cdc_leaves),
        "inventory_pairs": len(inventory_leaves),
        "r7_missing_pairs": len(missing_leaves),
        "r8_stale_pairs": len(truly_stale),
    }


def run_cdc_check(
    cfg: dict,
    *,
    print_cmd: bool = False,
    experimental: set[str] | None = None,
) -> dict:
    """Built-in: validate the CDC inventory against the v1 schema rules.

    ``experimental={"ast"}`` enables R7/R8 driver-enumeration rules when
    ``verible-verilog-syntax`` is on PATH. Without the flag (or with
    Verible missing), behaviour is byte-identical to the v0.8 regex
    pipeline plus the ``audit_engine`` disclosure field.
    """
    experimental = experimental or set()

    # Engine selection: AST path requires both the flag AND the binary.
    # Silent degrade-to-regex when the binary is missing — the
    # top-level warning from features.py already tells the user the
    # flag had no effect.
    engine = "regex"
    if "ast" in experimental:
        try:
            from . import verible_client
            if verible_client.ast_available():
                engine = "verible-ast"
        except ImportError:
            pass

    inv_path = _default_inventory_path(cfg)
    rel = str(inv_path.relative_to(cfg["_root"])) if inv_path.is_relative_to(cfg["_root"]) else str(inv_path)

    if print_cmd:
        return {
            "stage": "cdc-check",
            "status": "dry-run",
            "tool": "built-in-cdc-check",
            "audit_engine": engine,
            "inventory": rel,
        }

    findings: list[dict] = []

    if not inv_path.exists():
        return {
            "stage": "cdc-check",
            "status": "blocked",
            "tool": "built-in-cdc-check",
            "audit_engine": engine,
            "inventory": rel,
            "reason": f"inventory file not found: {rel}",
            "tail": (
                f"no CDC inventory at {rel}. Produce one by invoking the "
                "rtl-cdc-reviewer sub-agent (Claude Code) or /lp-cdc-review "
                "prompt (Codex), then re-run /lp-cdc-check."
            ),
        }

    try:
        inv = json.loads(inv_path.read_text())
    except json.JSONDecodeError as e:
        return {
            "stage": "cdc-check",
            "status": "fail",
            "tool": "built-in-cdc-check",
            "audit_engine": engine,
            "inventory": rel,
            "reason": f"JSON parse error at line {e.lineno}: {e.msg}",
            "tail": str(e),
        }

    structural_ok = _check_top_shape(inv, findings)
    crossings = inv.get("crossings", []) if structural_ok else []

    # R6: set_clock_groups_declared = false + non-empty crossings → fail.
    if (
        structural_ok
        and not inv.get("set_clock_groups_declared")
        and len(crossings) > 0
    ):
        _add(findings, "high", "cdc_clock_groups_not_declared", None,
             "set_clock_groups_declared=false but crossings are non-empty; "
             "STA needs `set_clock_groups -asynchronous` (or vendor "
             "equivalent) to skip CDC paths during timing analysis")

    # Per-crossing checks.
    by_verdict = {"safe": 0, "unsafe": 0, "waived": 0}
    for idx, x in enumerate(crossings):
        if not _check_crossing_shape(idx, x, findings):
            continue
        _check_verdict_required_fields(idx, x, findings)
        _check_truth_table(idx, x, findings)
        _check_conditional_fields(idx, x, findings)
        verdict = x.get("verdict")
        if verdict in by_verdict:
            by_verdict[verdict] += 1

    # R7 / R8: only when AST is actually available.
    ast_summary = None
    enumerated_drivers: list[dict] = []
    if engine == "verible-ast" and structural_ok:
        enumerated_drivers, _parsed = _enumerate_drivers(cfg)
        ast_summary = _check_r7_r8(inv, enumerated_drivers, findings)

    summary = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        summary[f["severity"]] = summary.get(f["severity"], 0) + 1

    status = "fail" if summary["high"] else "pass"
    tail_lines = [
        f"{f['severity'].upper()} "
        + (f"crossing[{f['crossing_index']}] " if 'crossing_index' in f else "")
        + f"{f['rule']} — {f['message']}"
        for f in findings[:25]
    ]
    tail = "\n".join(tail_lines) or (
        f"cdc-check passed: {len(crossings)} crossing(s) "
        f"({by_verdict['safe']} safe, {by_verdict['waived']} waived)"
    )

    result: dict[str, Any] = {
        "stage": "cdc-check",
        "status": status,
        "tool": "built-in-cdc-check",
        "audit_engine": engine,
        "inventory": rel,
        "crossings_total": len(crossings),
        "by_verdict": by_verdict,
        "summary": summary,
        "findings": findings,
        "tail": tail,
    }

    if ast_summary is not None:
        result["ast_enumeration"] = ast_summary
        # Cap the enumerated_drivers list so a giant design doesn't
        # blow up the JSON envelope.
        result["enumerated_drivers"] = enumerated_drivers[:_MAX_ENUMERATED_DRIVERS_IN_JSON]
        if len(enumerated_drivers) > _MAX_ENUMERATED_DRIVERS_IN_JSON:
            result.setdefault("warnings", []).append(
                f"enumerated_drivers truncated to "
                f"{_MAX_ENUMERATED_DRIVERS_IN_JSON} of {len(enumerated_drivers)} "
                "rows; rerun with smaller src globs to see all"
            )

    if status == "fail":
        result.setdefault("warnings", []).append(
            f"cdc-check failed: {summary['high']} blocking finding(s). "
            "Each row in 'findings' lists the crossing index + rule + fix."
        )

    return result
