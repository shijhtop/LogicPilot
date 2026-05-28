"""Built-in constraints stage — auto-generate baseline SDC from project
metadata + CDC inventory.

Why this exists:
  Every front-end project hand-writes the same five categories of SDC
  (primary clocks, async clock groups, CDC max_delay, false_path for
  reset / waived crossings, plus TODO markers for the rest). The
  inventory already has every clock and every legitimate async pair —
  re-typing it as SDC is repetitive and a known source of "inventory
  says safe but SDC forgot to declare the group" drift. This stage
  turns the inventory into a SDC file once per run.

Scope:
  - Primary `create_clock` for every clock declared in
    `cdc-inventory.json::clocks[]` (or, as a fallback, the single
    `[project].clock_mhz`).
  - `set_clock_groups -asynchronous` derived from every distinct
    `(from_clock, to_clock)` pair in `crossings[]`.
  - `set_max_delay` for safe CDC bus crossings carrying multi-bit data
    through a 2FF / 3FF synchronizer. The instance paths come straight
    out of `crossings[].signal` and `crossings[].evidence.module` —
    when those don't pin down enough hierarchy, the SDC line is emitted
    with a `<TODO: ...>` placeholder rather than guessed silently.
  - `set_false_path` for crossings explicitly waived (`verdict: waived`
    + `synchronizer: none`). Rationale is included as a comment so the
    SDC stays self-explanatory.

NOT generated (the docstring says so + the SDC's header comment says
so + the report stage flags them in `warnings`):
  - I/O delay (board-dependent — no source of truth).
  - `create_generated_clock` for PLLs / dividers (needs RTL parse to
    find the PLL instance and its config).
  - `set_multicycle_path` (user has to declare which paths are slow).

Envelope:
    {
      "stage": "constraints",
      "status": "pass" | "blocked" | "fail",
      "tool": "internal",
      "sdc_path": "build/auto.sdc",
      "summary": {
        "clocks_declared": N,
        "clock_groups_declared": N,
        "max_delays_declared": N,
        "false_paths_declared": N,
        "todo_placeholders": N,
      },
      "warnings": [...],
      "tail": "...last 25 lines of generated SDC...",
    }

This stage is OPT-IN — not in default `STAGE_ORDER`. Users add
`constraints` to `[pipeline].order` (typically right after `cdc-check`
and before `synth`) when they want the auto SDC. Projects that already
maintain hand-written SDC ignore the stage and nothing breaks.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class _ClockDecl:
    name: str
    period_ns: float
    port: str  # default = clock name (assumed top-level input port)


@dataclass(frozen=True)
class _CrossingDecl:
    from_clock: str
    to_clock: str
    signal: str           # e.g. "u_fifo.wr_ptr_gray"
    synchronizer: str     # 2ff / 3ff / handshake_req_ack / gray_counter / none
    verdict: str          # safe / unsafe / waived
    width: int
    rationale: str        # for waived
    evidence_module: str  # for max_delay hierarchy hints


_DEFAULT_OUTPUT = "build/auto.sdc"


# ---------- inventory loader (shared semantics with cdc_check) -------------


def _default_inventory_path(cfg: dict) -> Path:
    cdc_cfg = cfg.get("cdc", {}) if isinstance(cfg.get("cdc"), dict) else {}
    rel = str(cdc_cfg.get("inventory", "docs/cdc-inventory.json"))
    root: Path = cfg["_root"]
    return root / rel


def _load_inventory(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---------- clock + crossing extraction ------------------------------------


def _clocks_from_inventory(inv: dict) -> list[_ClockDecl]:
    """Pull declared clocks. Skip rows missing a usable period."""
    rows = inv.get("clocks") or []
    if not isinstance(rows, list):
        return []
    out: list[_ClockDecl] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        name = r.get("name")
        period = r.get("period_ns")
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(period, (int, float)) or period <= 0:
            continue
        port = r.get("port")
        port = port if isinstance(port, str) and port else name
        out.append(_ClockDecl(name=name, period_ns=float(period), port=port))
    return out


def _clocks_from_project(cfg: dict) -> list[_ClockDecl]:
    """Fallback: single primary clock from [project].clock_mhz."""
    proj = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    mhz = proj.get("clock_mhz")
    if not isinstance(mhz, (int, float)) or mhz <= 0:
        return []
    name = str(proj.get("clock_name", "clk"))
    period = round(1000.0 / float(mhz), 4)
    return [_ClockDecl(name=name, period_ns=period, port=name)]


def _crossings_from_inventory(inv: dict) -> list[_CrossingDecl]:
    rows = inv.get("crossings") or []
    if not isinstance(rows, list):
        return []
    out: list[_CrossingDecl] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        ev = r.get("evidence") if isinstance(r.get("evidence"), dict) else {}
        try:
            out.append(_CrossingDecl(
                from_clock=str(r.get("from_clock", "")),
                to_clock=str(r.get("to_clock", "")),
                signal=str(r.get("signal", "")),
                synchronizer=str(r.get("synchronizer", "")),
                verdict=str(r.get("verdict", "")),
                width=int(r.get("width") or 1),
                rationale=str(r.get("rationale") or ""),
                evidence_module=str(ev.get("module") or ""),
            ))
        except (TypeError, ValueError):
            continue
    return out


# ---------- SDC rendering --------------------------------------------------


_SYNCHRONIZERS_NEEDING_MAX_DELAY = frozenset({"2ff", "3ff", "mux_synchronizer"})


def _render_header(top: str, inventory_path: str | None) -> list[str]:
    return [
        "# Auto-generated by LogicPilot `constraints` stage.",
        "# DO NOT EDIT BY HAND — re-run `lp-constraints` to regenerate.",
        "#",
        f"# Top module: {top}",
        f"# Source of truth: {inventory_path or 'flow.toml [project].clock_mhz'}",
        "#",
        "# NOT auto-generated (you must supply these yourself):",
        "#   - set_input_delay / set_output_delay (board timing)",
        "#   - create_generated_clock for PLLs / dividers",
        "#   - set_multicycle_path (your slow-path annotations)",
        "",
    ]


def _render_create_clocks(clocks: list[_ClockDecl]) -> list[str]:
    if not clocks:
        return []
    lines = ["# --- Primary clocks ---"]
    for c in clocks:
        lines.append(
            f"create_clock -name {c.name} -period {c.period_ns:.3f} "
            f"[get_ports {c.port}]"
        )
    lines.append("")
    return lines


def _render_clock_groups(crossings: list[_CrossingDecl]) -> tuple[list[str], int]:
    """Emit one `set_clock_groups -asynchronous` covering every distinct
    (from, to) clock pair. Self-pair (same_clock) is rejected upstream by
    cdc-check; we defensively skip it here too.
    """
    pairs: set[tuple[str, str]] = set()
    for x in crossings:
        if not x.from_clock or not x.to_clock or x.from_clock == x.to_clock:
            continue
        pairs.add(tuple(sorted((x.from_clock, x.to_clock))))
    if not pairs:
        return [], 0
    lines = ["# --- Async clock groups ---"]
    for a, b in sorted(pairs):
        lines.append(
            f"set_clock_groups -asynchronous -group {{{a}}} -group {{{b}}}"
        )
    lines.append("")
    return lines, len(pairs)


def _signal_to_hier(signal: str) -> str:
    """Translate `u_fifo.wr_ptr_gray` → `*/u_fifo/wr_ptr_gray*` glob
    for `get_cells` / `get_pins`. Synthesis flattens hierarchy; the
    leading `*/` walks any prefix the synth tool added."""
    if not signal:
        return ""
    return "*/" + signal.replace(".", "/")


def _render_max_delays(
    crossings: list[_CrossingDecl],
    clock_periods: dict[str, float],
) -> tuple[list[str], int, int]:
    """Emit `set_max_delay` for safe multi-bit CDC bus crossings through
    a 2FF / 3FF synchronizer. Returns (lines, count, todo_count).
    todo_count = lines where we had to drop a TODO placeholder for the
    sync-flop instance path."""
    relevant = [
        x for x in crossings
        if x.synchronizer in _SYNCHRONIZERS_NEEDING_MAX_DELAY
        and x.verdict == "safe"
    ]
    if not relevant:
        return [], 0, 0
    lines = [
        "# --- CDC bus max_delay ---",
        "# Bound source-to-sync flop skew to ONE source-clock period so",
        "# the multi-bit value stays coherent through the synchronizer.",
    ]
    todos = 0
    for x in relevant:
        period = clock_periods.get(x.from_clock)
        if period is None:
            lines.append(
                f"# WARN: source clock '{x.from_clock}' has no declared "
                "period — skipped"
            )
            continue
        src_hier = _signal_to_hier(x.signal)
        # The destination synchronizer instance lives somewhere under the
        # evidence module but the inventory doesn't pin the leaf instance.
        # Emit the bound + a TODO so the user finishes the -to clause.
        lines.append(
            f"set_max_delay {period:.3f} \\\n"
            f"    -from [get_cells {{{src_hier}*}}] \\\n"
            f"    -to   [get_pins  {{<TODO: sync first-FF D pin in "
            f"{x.evidence_module or 'destination domain'}>}}]"
        )
        todos += 1
    lines.append("")
    return lines, len(relevant), todos


def _render_false_paths(crossings: list[_CrossingDecl]) -> tuple[list[str], int]:
    """`set_false_path` for waived unprotected crossings. Inventory
    enforces rationale + evidence on waived rows so we always have a
    self-documenting comment to attach."""
    relevant = [
        x for x in crossings
        if x.verdict == "waived" and x.synchronizer == "none"
    ]
    if not relevant:
        return [], 0
    lines = [
        "# --- Waived crossings (false_path) ---",
        "# Each entry below was waived in the CDC inventory; the rationale",
        "# is shown for review.",
    ]
    for x in relevant:
        lines.append(f"# waiver rationale: {x.rationale or '(no rationale recorded)'}")
        src_hier = _signal_to_hier(x.signal)
        lines.append(f"set_false_path -through [get_pins {{{src_hier}*}}]")
    lines.append("")
    return lines, len(relevant)


# ---------- entry point ----------------------------------------------------


def run_constraints(cfg: dict, *, print_cmd: bool = False) -> dict:
    """Generate `build/auto.sdc` from the CDC inventory + project clocks."""
    root: Path = cfg["_root"]
    proj = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    build_dir = root / proj.get("build_dir", "build")

    constraints_cfg = (
        cfg.get("constraints", {}) if isinstance(cfg.get("constraints"), dict) else {}
    )
    output_rel = str(constraints_cfg.get("output") or _DEFAULT_OUTPUT)

    # Safe-mode path confinement: when --gate-untrusted is active, refuse
    # any output path that doesn't resolve under the project root.
    #
    # Two layers of defence — both required:
    #
    #   1. Lexical check: reject absolute paths and `..` traversal. Catches
    #      the obvious "/etc/passwd" / "../../foo" cases without touching
    #      the filesystem.
    #
    #   2. Symlink-resolved check: walk `(root / output).resolve()` and
    #      require it stays under `root.resolve()`. This defeats the
    #      symlink bypass — `[constraints].output = "link/auto.sdc"`
    #      where the repo contains a `link` symlink pointing at `/etc/`
    #      would pass the lexical check (path is relative, no `..`), but
    #      resolve() follows the symlink to /etc/auto.sdc which is outside
    #      the root and gets rejected here.
    #
    # `strict=False` so the target file (which doesn't exist yet)
    # doesn't error; intermediate symlinks ARE resolved.
    safe_mode = bool(cfg.get("_safe_preset_only"))
    output_raw = Path(output_rel)
    if safe_mode:
        if output_raw.is_absolute() or ".." in output_raw.parts:
            return {
                "stage": "constraints",
                "status": "blocked",
                "tool": "internal",
                "reason": (
                    f"safe-preset mode rejects out-of-root constraints output "
                    f"path {output_rel!r}. Use a path under the project root "
                    "(e.g. 'build/auto.sdc'), or trust the project on this "
                    "machine and re-run without --gate-untrusted."
                ),
                "warnings": [],
                "tail": "(blocked before any write)",
            }
        candidate = root / output_raw
        try:
            # Force-detect symlink loops via os.stat. We can't rely on
            # `Path.resolve(strict=False)` alone — Python 3.13+ changed
            # that path to silently return on symlink loops instead of
            # raising RuntimeError. `os.stat(..., follow_symlinks=True)`
            # always raises OSError(ELOOP) on every Python version, so
            # walk up to the first path component that actually exists
            # (or IS a symlink) and stat it. This catches:
            #   - self-referential symlinks (`loop → loop`)
            #   - mutual symlinks (`a → b`, `b → a`)
            #   - too-deep symlink chains
            # on Python 3.10 through 3.13+ uniformly.
            probe = candidate
            while (not probe.exists() and not probe.is_symlink()
                   and probe != probe.parent):
                probe = probe.parent
            if probe != probe.parent:
                # Reached an existing dir or a symlink — stat it (follows
                # symlinks, raising on any loop in the chain).
                os.stat(probe, follow_symlinks=True)

            # Lexical confinement check: where does the path RESOLVE to?
            # If outside `root.resolve()` (e.g. via `link → /etc/`),
            # `relative_to` raises ValueError.
            resolved_target = candidate.resolve(strict=False)
            resolved_root = root.resolve(strict=False)
            resolved_target.relative_to(resolved_root)
        except (ValueError, RuntimeError, OSError) as exc:
            reason = (
                f"safe-preset mode rejects constraints output path "
                f"{output_rel!r}: "
            )
            err_no = getattr(exc, "errno", None)
            import errno as _errno  # noqa: PLC0415 — keep stdlib lazy-import local
            if err_no == _errno.ELOOP or (
                isinstance(exc, RuntimeError) and "loop" in str(exc).lower()
            ):
                reason += "symlink loop detected during path resolution."
            elif isinstance(exc, OSError):
                reason += f"filesystem error during path resolution ({exc})."
            else:
                reason += (
                    "it resolves outside the project root (likely via a symlink)."
                )
            reason += (
                f" Use a path that resolves under {root}, or trust the project "
                "on this machine and re-run without --gate-untrusted."
            )
            return {
                "stage": "constraints",
                "status": "blocked",
                "tool": "internal",
                "reason": reason,
                "warnings": [],
                "tail": "(blocked before any write)",
            }
    output_path = root / output_raw if not output_raw.is_absolute() else output_raw

    inv_path = _default_inventory_path(cfg)
    inv = _load_inventory(inv_path)
    warnings: list[str] = []

    # Source of clocks: inventory.clocks (preferred) → project.clock_mhz fallback.
    if inv is not None:
        clocks = _clocks_from_inventory(inv)
        crossings = _crossings_from_inventory(inv)
        inv_path_display = str(inv_path.relative_to(root)) if root in inv_path.parents else str(inv_path)
    else:
        clocks = _clocks_from_project(cfg)
        crossings = []
        inv_path_display = None
        if inv_path.exists():
            warnings.append(f"inventory at {inv_path} could not be parsed as JSON")
        else:
            warnings.append(
                "no CDC inventory found; falling back to single-clock SDC from "
                "[project].clock_mhz only — no clock groups / max_delays / "
                "false_paths will be generated"
            )

    if not clocks:
        return {
            "stage": "constraints",
            "status": "blocked",
            "tool": "internal",
            "reason": (
                "no clocks declared — set [project].clock_mhz, or add a "
                "clocks[] array to docs/cdc-inventory.json with at least "
                "{name, period_ns}"
            ),
            "warnings": warnings,
            "tail": "(no SDC written)",
        }

    top = str(proj.get("top", "top"))
    clock_periods = {c.name: c.period_ns for c in clocks}

    cmd_repr = f"<internal: lp-constraints → {output_rel}>"
    if print_cmd:
        return {
            "stage": "constraints",
            "status": "dry-run",
            "tool": "internal",
            "sdc_path": output_rel,
            "cmd": cmd_repr,
        }

    lines: list[str] = []
    lines += _render_header(top, inv_path_display)
    lines += _render_create_clocks(clocks)
    group_lines, n_groups = _render_clock_groups(crossings)
    lines += group_lines
    delay_lines, n_delays, n_todos = _render_max_delays(crossings, clock_periods)
    lines += delay_lines
    false_lines, n_false = _render_false_paths(crossings)
    lines += false_lines

    try:
        build_dir.mkdir(parents=True, exist_ok=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(lines).rstrip() + "\n"
        output_path.write_text(text)
    except OSError as exc:
        return {
            "stage": "constraints",
            "status": "fail",
            "tool": "internal",
            "reason": f"cannot write SDC to {output_path}: {exc}",
            "warnings": warnings,
            "tail": "(write failed)",
        }

    if n_todos:
        warnings.append(
            f"{n_todos} `set_max_delay` line(s) carry a <TODO> placeholder for "
            "the destination synchronizer's first-FF D pin — fill in the "
            "instance path before sign-off."
        )

    tail = "\n".join(text.splitlines()[-25:]) or "(empty SDC)"
    return {
        "stage": "constraints",
        "status": "pass",
        "tool": "internal",
        "sdc_path": output_rel,
        "summary": {
            "clocks_declared": len(clocks),
            "clock_groups_declared": n_groups,
            "max_delays_declared": n_delays,
            "false_paths_declared": n_false,
            "todo_placeholders": n_todos,
        },
        "warnings": warnings,
        "tail": tail,
    }
