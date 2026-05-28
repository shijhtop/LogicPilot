"""AST-only audit rules (post-v1.0, requires --experimental-ast + Verible).

These are rules regex genuinely can't get right because they need to
COMPARE assignments across blocks / files. The regex audit path catches
single-line traps (delay control, casex, DPI in RTL); the AST path adds
checks that require cross-block reasoning.

Rules implemented in this round:

- ``ast_multi_driver`` (HIGH): one signal is the LHS of assignments in
  MORE THAN ONE always/assign block. In synthesizable RTL this is
  almost always a real defect — vendor synthesis will warn or pick a
  driver arbitrarily, simulator + synth may disagree.

- ``ast_clocked_vs_comb_mix`` (HIGH): one signal is driven by an
  edge-triggered block AND a combinational block. This is strictly
  worse than plain multi-driver — the combinational path will fight
  the flip-flop and the result is undefined.

Both rules dedupe on signal-leaf name (matches the cdc-check hierarchy
collapse rule). Two driver instances of ``u_a.foo`` and ``u_b.foo`` in
different module instances DO collapse to one finding here — accepted
trade-off: this is meant as a "hey, look at this" signal, not a
precise multi-driver linter, and the finding message points at the
file:line so the human can verify.

Findings come back in the standard ``audit`` finding shape so the
existing JSON envelope (`summary`, `findings`, `tail`) absorbs them
without further plumbing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import verible_client


def _add(
    findings: list[dict],
    severity: str,
    rule: str,
    rel_path: str,
    line: int,
    message: str,
) -> None:
    findings.append({
        "severity": severity,
        "rule": rule,
        "file": rel_path,
        "line": line,
        "message": message,
    })


def run_ast_rules(files: list[Path], root: Path) -> list[dict]:
    """Run every AST-only audit rule across ``files``; return findings.

    Verible binary missing OR any file unparseable → that file is
    silently skipped (the engine-disclosure field on the parent audit
    envelope already tells the user the AST path was attempted).
    Returns ``[]`` when ``ast_available()`` is False, so callers
    don't need a separate guard.
    """
    if not verible_client.ast_available():
        return []

    # Build the cross-file driver index:
    #   leaf_signal -> [{kind, file, line}, ...]
    drivers: dict[str, list[dict[str, Any]]] = {}

    for src in files:
        ast = verible_client.parse_file(src)
        if not ast:
            continue
        try:
            rel = str(src.relative_to(root))
        except ValueError:
            rel = str(src)
        for signal, kind, line in verible_client.iter_all_assignments(ast):
            leaf = signal.rsplit(".", 1)[-1]
            drivers.setdefault(leaf, []).append({
                "kind": kind,
                "file": rel,
                "line": line,
            })

    findings: list[dict] = []
    _check_multi_driver(drivers, findings)
    _check_clocked_vs_comb_mix(drivers, findings)
    return findings


def _check_multi_driver(
    drivers: dict[str, list[dict[str, Any]]],
    findings: list[dict],
) -> None:
    """Signal driven by >1 always/assign block → fail.

    Continuous-assign-to-the-same-signal counts as a driver too.
    Reports the FIRST occurrence's location with the count of total
    drivers in the message — the human chases the rest from the
    file:line.
    """
    for leaf, locs in drivers.items():
        if len(locs) <= 1:
            continue
        first = locs[0]
        rest = ", ".join(
            f"{loc['file']}:{loc['line']} ({loc['kind']})"
            for loc in locs[1:]
        )
        _add(
            findings,
            "high",
            "ast_multi_driver",
            first["file"],
            first["line"],
            f"signal '{leaf}' is driven by {len(locs)} blocks "
            f"(first here, others: {rest}); synthesizable RTL must "
            "have exactly one driver per net",
        )


def _check_clocked_vs_comb_mix(
    drivers: dict[str, list[dict[str, Any]]],
    findings: list[dict],
) -> None:
    """Signal driven by BOTH clocked and combinational block → fail.

    This is the worst flavor of multi-driver: the comb path fights
    the FF every cycle. Strictly a subset of multi-driver but called
    out separately because it has a different fix (one of the two
    paths is wrong, not "merge them").

    Suppresses redundant noise: if multi-driver already fired for
    this leaf, we still emit this finding because the FIX is
    different and the human needs to see the distinction.
    """
    for leaf, locs in drivers.items():
        kinds = {loc["kind"] for loc in locs}
        if "clocked" in kinds and "comb" in kinds:
            first_clocked = next(loc for loc in locs if loc["kind"] == "clocked")
            first_comb = next(loc for loc in locs if loc["kind"] == "comb")
            _add(
                findings,
                "high",
                "ast_clocked_vs_comb_mix",
                first_clocked["file"],
                first_clocked["line"],
                f"signal '{leaf}' is driven by both a clocked block "
                f"({first_clocked['file']}:{first_clocked['line']}) "
                f"and a combinational block "
                f"({first_comb['file']}:{first_comb['line']}); "
                "one of them is wrong — clocked fights comb every "
                "cycle and synthesis result is undefined",
            )
