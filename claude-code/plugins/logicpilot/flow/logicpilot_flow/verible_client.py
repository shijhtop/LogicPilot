"""Verible CLI client (v1.0+ experimental-ast wiring).

Stdlib-only wrapper around ``verible-verilog-syntax --export_json`` that
exposes just enough of the AST for the audit / cdc-check stages.

Why a CLI shell and not a Python binding?
  Verible's only first-party API is C++. PyO3-style bindings would push
  LogicPilot off the "Python 3.11+ stdlib only" promise and force a
  per-platform wheel matrix. The CLI is a portable, slow-ish, but
  zero-dependency seam.

When the binary is missing OR the AST cannot be parsed, every entry
point returns ``None`` (or yields nothing). Callers MUST tolerate this
and fall back to the regex path — the AST engine is best-effort.

Public surface (intentionally small):

- ``ast_available()`` -> bool   — quick PATH probe
- ``parse_file(path)`` -> dict | None   — full AST for one file
- ``iter_clocked_drivers(ast)``  — yield (clock, signal, line) for every
  identifier driven inside an edge-triggered always block

Verible AST node tags this module relies on (only the ones we need —
the full grammar is in ``verible/verilog/CST/verilog_nonterminals.h``):

- ``kAlwaysStatement``               whole ``always_ff``/``always @(...)`` block
- ``kProceduralTimingControlStatement`` wraps the event-control + body
- ``kEventControl``                  ``@(posedge clk, ...)`` clause
- ``kAlwaysFFHeader``                ``always_ff @(...)`` header
- ``kEventExpressionList`` / ``kEventExpression`` sensitivity items
- ``kNonblockingAssignmentStatement`` ``lhs <= rhs;``
- ``kBlockingAssignmentStatement``   ``lhs = rhs;``
- ``kLPValue``                       LHS of an assignment
- ``kReference`` / ``kReferenceCallBase`` identifier reference
- ``SymbolIdentifier``               leaf identifier token

Identifier leaves come back as
``{"tag": "SymbolIdentifier", "start": [line, col], "end": [...], "text": "name"}``.

Internal nodes look like
``{"tag": "kFoo", "children": [...]}``.

Either form may be ``None`` to represent an omitted optional production.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterator, Optional


_BINARY = "verible-verilog-syntax"
_PARSE_TIMEOUT_S = 10.0

# Per-process AST cache keyed on (resolved_path, mtime_ns).
# Verible parses are pure functions of file bytes; mtime change invalidates.
_AST_CACHE: dict[tuple[str, int], Optional[dict]] = {}


def ast_available() -> bool:
    """Return True iff ``verible-verilog-syntax`` is on PATH.

    Cheap — just a PATH lookup, no subprocess fork. Cache caller-side
    if you call this in a hot loop.
    """
    return shutil.which(_BINARY) is not None


def parse_file(path: Path, *, timeout_s: float = _PARSE_TIMEOUT_S) -> Optional[dict]:
    """Parse one Verilog/SystemVerilog file and return its AST as a dict.

    Returns ``None`` on every failure mode (binary missing, syntax
    error, subprocess timeout, unparseable JSON, file unreadable). The
    None contract lets callers do ``ast or fallback()`` without
    try/except plumbing.

    The output dict is Verible's raw ``--export_json`` envelope:

        {
          "<file_path>": {
            "tree": { "tag": "kVerilogSource", "children": [...] },
            "rawTokens": [...]
          }
        }

    We do NOT normalize that — the iterators below take this shape as
    input directly.
    """
    if not ast_available():
        return None
    try:
        resolved = path.resolve()
        stat = resolved.stat()
    except OSError:
        return None

    key = (str(resolved), stat.st_mtime_ns)
    if key in _AST_CACHE:
        return _AST_CACHE[key]

    try:
        proc = subprocess.run(
            [_BINARY, "--export_json", str(resolved)],
            capture_output=True, text=True, timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        _AST_CACHE[key] = None
        return None

    # Verible returns non-zero on syntax errors but still emits a
    # partial tree. We prefer to return None in that case so callers
    # don't draw conclusions from an incomplete walk.
    if proc.returncode != 0 or not proc.stdout.strip():
        _AST_CACHE[key] = None
        return None

    try:
        ast = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _AST_CACHE[key] = None
        return None

    _AST_CACHE[key] = ast
    return ast


def _walk(node: Optional[dict | list]) -> Iterator[dict]:
    """Depth-first walk that yields every dict node in the tree."""
    if node is None:
        return
    if isinstance(node, list):
        for child in node:
            yield from _walk(child)
        return
    if not isinstance(node, dict):
        return
    yield node
    children = node.get("children")
    if children is not None:
        yield from _walk(children)


def _first_identifier_text(node: Optional[dict | list]) -> Optional[str]:
    """Return the text of the first ``SymbolIdentifier`` under ``node``.

    Used to extract the clock name from an event-control subtree (the
    identifier that follows ``posedge``/``negedge``) and the lvalue
    name from an assignment LHS subtree.
    """
    for n in _walk(node):
        if n.get("tag") == "SymbolIdentifier":
            text = n.get("text")
            if isinstance(text, str) and text:
                return text
    return None


def _identifier_with_line(node: Optional[dict | list]) -> tuple[Optional[str], Optional[int]]:
    """Return (text, line_no) of the first SymbolIdentifier."""
    for n in _walk(node):
        if n.get("tag") == "SymbolIdentifier":
            text = n.get("text")
            start = n.get("start")
            line = start[0] if isinstance(start, list) and start else None
            if isinstance(text, str) and text:
                return text, line
    return None, None


def _edge_triggered_clock(event_ctrl: dict) -> Optional[str]:
    """Extract the clock identifier from a ``kEventControl`` subtree.

    Convention: the first identifier appearing immediately after a
    ``posedge``/``negedge`` token is the clock. We tolerate either
    plain ``@(posedge clk)`` or ``@(posedge clk_a or negedge rst_n)`` —
    only the first is returned.
    """
    # Walk tokens in order; remember whether the previous interesting
    # token was an edge keyword, then return the next identifier.
    edge_seen = False
    for n in _walk(event_ctrl):
        tag = n.get("tag")
        if tag in {"posedge", "negedge"} or (
            isinstance(tag, str) and tag.lower() in {"posedge", "negedge"}
        ):
            edge_seen = True
            continue
        if edge_seen and tag == "SymbolIdentifier":
            text = n.get("text")
            if isinstance(text, str) and text:
                return text
    return None


# Always-block header tags we recognise. ``kAlwaysFFHeader`` is the
# SystemVerilog ``always_ff`` form; the plain ``always @(posedge …)``
# form is exposed as ``kAlwaysStatement`` + child ``kProceduralTiming
# ControlStatement`` + grandchild ``kEventControl``.
_ALWAYS_NODE_TAGS = {"kAlwaysStatement", "kAlwaysFFStatement"}
_ASSIGN_NODE_TAGS = {
    "kNonblockingAssignmentStatement",
    "kBlockingAssignmentStatement",
    "kAssignmentStatement",
}


def iter_clocked_drivers(ast: Optional[dict]) -> Iterator[tuple[str, str, int]]:
    """Yield (clock_name, lhs_signal, line_no) for every clocked driver.

    Walks every ``kAlwaysStatement`` in the AST. For blocks whose event
    control contains an edge trigger, every LHS identifier of an
    assignment inside the block is treated as a driver in that clock
    domain. Signals are returned in their textual form, NOT resolved
    against any module hierarchy — the caller is responsible for
    anchoring against ``top_module`` per the cdc-inventory schema.

    Conservative by design: we skip combinational always blocks
    (no edge keyword), skip assignments whose lvalue is purely indexed
    or concatenated (the first identifier is still yielded — good
    enough for inventory diffing), and de-dupe at the call site.
    """
    if not ast:
        return

    # Verible emits one top-level entry per parsed file. Walk all of
    # them — a multi-file call wraps each parse under its file key.
    for _file_key, file_payload in (ast.items() if isinstance(ast, dict) else []):
        if not isinstance(file_payload, dict):
            continue
        tree = file_payload.get("tree")
        if not isinstance(tree, dict):
            continue

        for node in _walk(tree):
            if node.get("tag") not in _ALWAYS_NODE_TAGS:
                continue

            # Find the event-control subtree under this always block.
            event_ctrl = None
            for sub in _walk(node):
                if sub.get("tag") == "kEventControl":
                    event_ctrl = sub
                    break
            if event_ctrl is None:
                continue

            clock = _edge_triggered_clock(event_ctrl)
            if not clock:
                # Comb / latch block — irrelevant for CDC enumeration.
                continue

            # Walk the always body for assignments.
            for sub in _walk(node):
                if sub.get("tag") not in _ASSIGN_NODE_TAGS:
                    continue
                # The first child of an assignment is the LHS subtree
                # (kLPValue or similar). We extract its first
                # identifier as the driven signal name.
                children = sub.get("children") or []
                lhs_subtree = children[0] if children else sub
                signal, line = _identifier_with_line(lhs_subtree)
                if signal and isinstance(line, int):
                    yield clock, signal, line


def iter_all_assignments(
    ast: Optional[dict],
) -> Iterator[tuple[str, str, int]]:
    """Yield ``(signal, block_kind, line_no)`` for every assignment in ``ast``.

    ``block_kind`` is one of:

    - ``"clocked"`` — assignment inside an edge-triggered always block
      (e.g. ``always_ff`` or ``always @(posedge clk)``). These are
      flip-flop drivers.
    - ``"comb"`` — assignment inside an always block whose event control
      is empty or has no edge keyword (``always_comb``, ``always @*``,
      ``always @(a or b)``). These should produce combinational logic
      OR an unintended latch.
    - ``"continuous"`` — ``assign sig = ...;`` at module scope. Also
      combinational, but with no inferred-latch risk.

    Used by audit_ast.py for cross-block rules (multi-driver,
    clocked/comb mixing) and for future implicit-latch detection.
    Conservative on edge cases: only the leftmost SymbolIdentifier of
    an assignment LHS is reported (matches iter_clocked_drivers).
    """
    if not ast:
        return

    for _file_key, file_payload in (ast.items() if isinstance(ast, dict) else []):
        if not isinstance(file_payload, dict):
            continue
        tree = file_payload.get("tree")
        if not isinstance(tree, dict):
            continue

        # 1) always blocks
        for node in _walk(tree):
            if node.get("tag") not in _ALWAYS_NODE_TAGS:
                continue
            event_ctrl = None
            for sub in _walk(node):
                if sub.get("tag") == "kEventControl":
                    event_ctrl = sub
                    break
            # Classify the block.
            if event_ctrl is not None and _edge_triggered_clock(event_ctrl):
                kind = "clocked"
            else:
                kind = "comb"
            # Pull every assignment LHS inside the block body.
            for sub in _walk(node):
                if sub.get("tag") not in _ASSIGN_NODE_TAGS:
                    continue
                children = sub.get("children") or []
                lhs_subtree = children[0] if children else sub
                signal, line = _identifier_with_line(lhs_subtree)
                if signal and isinstance(line, int):
                    yield signal, kind, line

        # 2) continuous assigns (``assign foo = ...;`` at module scope)
        for node in _walk(tree):
            if node.get("tag") != "kContinuousAssignmentStatement":
                continue
            # Continuous assign's first child is typically the LHS net.
            children = node.get("children") or []
            lhs_subtree = children[0] if children else node
            signal, line = _identifier_with_line(lhs_subtree)
            if signal and isinstance(line, int):
                yield signal, "continuous", line


def clear_cache() -> None:
    """Drop the in-process AST cache. For tests / long-running drivers."""
    _AST_CACHE.clear()
