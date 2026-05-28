"""Built-in formal stage (v1.1+ preview, --experimental-formal).

Vendor-agnostic dispatch: the `formal` stage inspects PATH for any
supported backend (sby / jaspergold / vcf / qverify), uses the first
one available, and emits a unified JSON envelope so downstream agents
don't need to know which proof engine ran.

Today only the **SBY** backend (SymbiYosys + yosys + SMT solver) has
a real implementation — it's the only formal frontend that's free,
runs anywhere LogicPilot does, and produces parseable text output. The
commercial backends (Cadence JasperGold, Synopsys VC Formal, Siemens
Questa Formal) are registered in the candidate list and their probe
binaries are looked up on PATH, but their output parsers are stubs
that return `status: blocked` with a "vendor parser not yet
implemented" reason and a pointer to file an issue with an anonymized
log sample. The envelope shape is frozen now so when a contributor
with a license adds a parser, no contract breakage happens.

Stage is hidden behind `--experimental-formal`. Without the flag,
calling `formal` returns `blocked` + an instruction to add it. The
flag is registered in features.py with status="preview".

Envelope (v1 frozen — additive evolution only):

    {
      "stage": "formal",
      "status": "pass" | "fail" | "blocked" | "timeout",
      "tool": "sby" | "jaspergold" | "vcf" | "qverify" | null,
      "mode": "bmc" | "prove" | "cover" | "live",
      "depth": int,
      "engine_used": "smtbmc z3" | ...,        # backend-specific string
      "properties": { "name": "PASS|FAIL|UNKNOWN", ... },
      "counterexamples": [
        { "property": "name", "trace": "path/to/trace.vcd", "depth_hit": N }
      ],
      "summary": { "pass": N, "fail": N, "unknown": N },
      "requested_properties": ["a", "b"],       # only when [formal].properties set
      "warnings": [...],
      "tail": "...last 25 lines of sby log...",
      "install_hint": {...}                     # only when blocked on missing tool
    }

Filtering: when ``[formal].properties = ["a", "b"]`` is set, the
envelope reports only those names and the status is computed from the
filtered subset (a top-level ``DONE(PASS)`` is ignored if the requested
properties never appeared in the log — that's a "you asked, we didn't
prove it" fail). Each requested-but-missing name shows up as a
``warnings`` row.

``counterexamples[].depth_hit`` is extracted on a best-effort basis from
SBY's ``BMC failed at step N`` / ``Checking assert in step N`` markers.
None when SBY's output doesn't carry one — agents must treat the field
as optional.

Configuration (`[formal]` section of flow.toml):

    [formal]
    mode = "prove"                 # bmc | prove | cover | live
    depth = 20                     # search depth in cycles
    engines = ["smtbmc z3"]        # backend-specific; first that solves wins
    top = "fifo"                   # default: [project].top
    properties = []                # empty = run all assertions; list scopes
    timeout_s = 600                # per-stage budget

Why the SBY-only-parser stance?
  Commercial formal tools produce vendor-specific session-log
  directories (jgproject/, vcs/, qverify_log/) plus proprietary trace
  formats (vstf, fsdb). Writing parsers from a spec without a license
  to test against produces guesses that break in production. We
  scaffold the dispatch + envelope + install_hint today; the parsers
  land when someone with the tool can verify.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import _expand_globs
from .install_hints import hints_for


# Ordered list: first backend on PATH wins.
_BACKEND_PROBES: tuple[tuple[str, str], ...] = (
    ("sby",        "sby"),
    ("jaspergold", "jaspergold"),
    ("vcf",        "vcf"),
    ("qverify",    "qverify"),
)


_DEFAULT_TIMEOUT_S = 600
_VALID_MODES = ("bmc", "prove", "cover", "live")


def _formal_cfg(cfg: dict) -> dict:
    raw = cfg.get("formal")
    return raw if isinstance(raw, dict) else {}


def _pick_backend(formal_cfg: dict) -> tuple[str | None, str | None]:
    """Return (backend_name, binary_path) for the first installed backend.

    If `[formal].backend = "sby"` is set, restrict to that one only.
    Returns (None, None) when no usable backend is on PATH.
    """
    pinned = formal_cfg.get("backend")
    if isinstance(pinned, str) and pinned:
        # Honor explicit pin; will return None if the pinned tool isn't installed.
        for name, probe in _BACKEND_PROBES:
            if name == pinned:
                path = shutil.which(probe)
                return (name, path) if path else (None, None)
        return (None, None)

    for name, probe in _BACKEND_PROBES:
        path = shutil.which(probe)
        if path:
            return name, path
    return None, None


def _blocked(
    reason: str,
    *,
    missing_tools: list[str] | None = None,
    tail: str | None = None,
) -> dict:
    out: dict[str, Any] = {
        "stage": "formal",
        "status": "blocked",
        "tool": None,
        "reason": reason,
        "tail": tail or reason,
    }
    if missing_tools:
        out["missing"] = missing_tools
        hints = hints_for(missing_tools)
        if hints:
            out["install_hint"] = hints
    return out


def _resolve_sources(cfg: dict) -> list[Path]:
    """Pull RTL Verilog/SV source paths from the project."""
    proj = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    root: Path = cfg["_root"]
    patterns = proj.get("src_ordered", proj.get("src", []))
    out: list[Path] = []
    seen: set[Path] = set()
    for f in _expand_globs(patterns, root):
        p = Path(f)
        if not p.is_absolute():
            p = root / p
        if p.exists() and p.suffix.lower() in {".v", ".vh", ".sv", ".svh"}:
            r = p.resolve()
            if r not in seen:
                out.append(r)
                seen.add(r)
    return out


# --- SBY backend -----------------------------------------------------------

def _render_sby(
    formal_cfg: dict,
    top: str,
    src_files: list[Path],
    work_dir: Path,
) -> str:
    """Render the .sby config text fed to SymbiYosys."""
    mode = str(formal_cfg.get("mode", "prove")).lower()
    if mode not in _VALID_MODES:
        mode = "prove"
    depth = int(formal_cfg.get("depth", 20))
    raw_engines = formal_cfg.get("engines") or ["smtbmc z3"]
    if isinstance(raw_engines, str):
        raw_engines = [raw_engines]
    engines = "\n".join(str(e) for e in raw_engines)

    # Use ABSOLUTE paths so SBY can find files from its work dir.
    read_cmd_files = " ".join(str(p) for p in src_files)
    files_section = "\n".join(str(p) for p in src_files)

    return (
        "[options]\n"
        f"mode {mode}\n"
        f"depth {depth}\n"
        "\n"
        "[engines]\n"
        f"{engines}\n"
        "\n"
        "[script]\n"
        f"read -sv {read_cmd_files}\n"
        f"prep -top {top}\n"
        "\n"
        "[files]\n"
        f"{files_section}\n"
    )


# Property-failure marker. SBY 0.20+ emits, per engine:
#   "Assert failed in <module>: <file>:<line> (<name>)"
# Older versions sometimes drop the parenthesized name. Tolerant regex.
_SBY_ASSERT_FAILED_RE = re.compile(
    r"Assert failed in (?P<module>\S+):\s*(?P<file>\S+?):(?P<line>\d+)"
    r"(?:\s*\((?P<name>[^)]+)\))?",
)
# Per-engine trace dump:
#   "Writing trace to VCD file: engine_0/trace.vcd"
_SBY_TRACE_RE = re.compile(
    r"Writing trace to (?:VCD|FST|witness) file:\s+(?P<path>\S+)",
    re.IGNORECASE,
)
# Per-engine status:
#   "Status: PASSED" / "Status: FAILED" / "Status: UNKNOWN"
_SBY_STATUS_RE = re.compile(r"Status:\s+(PASSED|FAILED|UNKNOWN)", re.IGNORECASE)
# Top-level done marker:
#   "DONE (PASS, rc=0)" / "DONE (FAIL, rc=2)" / "DONE (UNKNOWN, rc=4)"
_SBY_DONE_RE = re.compile(
    r"DONE\s*\(\s*(?P<verdict>PASS|FAIL|UNKNOWN)\s*(?:,\s*rc=(?P<rc>\d+))?\)",
    re.IGNORECASE,
)
# Engine identification: "engine_0:" lines tell us which engine produced what.
_SBY_ENGINE_LINE_RE = re.compile(r"engine_(?P<idx>\d+):")
# Explicit failure-step markers SBY emits in BMC / cover mode. Different
# SBY versions / engines pick slightly different wording, so be tolerant.
#   "BMC failed at step 5"
#   "Reached cover statement at step 12"
#   "Counterexample found at depth 7"
_SBY_FAIL_STEP_RE = re.compile(
    r"(?:BMC failed|cover.*?reached|cover.*?hit|counter[- ]?example.*?found)"
    r".*?(?:at\s+)?(?:step|depth)\s+(\d+)",
    re.IGNORECASE,
)
# Step trace SBY prints when verbose: "Checking assert in step 5..". Used as
# fallback — the largest step seen before "Assert failed" is the failure depth.
_SBY_STEP_TRACE_RE = re.compile(
    r"Checking (?:assert|assertion)s?\s+(?:in|at)\s+step\s+(\d+)",
    re.IGNORECASE,
)


def _extract_depth_hit(prefix: str) -> int | None:
    """Pull the cycle/step at which SBY reported the failure.

    ``prefix`` is the slice of SBY stdout from the start of the run up to
    and including the ``Assert failed`` line. In a multi-failure log the
    prefix for the N-th assertion already contains every earlier
    ``BMC failed at step …`` marker, so use the **last** match in the
    prefix (nearest to the assertion line) — taking the first match would
    misattribute every later failure to the first failure's step.
    Returns None when no recognisable step marker is present.
    """
    explicit_hits = [int(m.group(1)) for m in _SBY_FAIL_STEP_RE.finditer(prefix)]
    if explicit_hits:
        return explicit_hits[-1]
    steps = [int(m.group(1)) for m in _SBY_STEP_TRACE_RE.finditer(prefix)]
    if steps:
        return max(steps)
    return None


def _parse_sby_output(
    stdout: str, work_dir: Path
) -> tuple[dict[str, str], list[dict[str, Any]], str | None]:
    """Parse SBY stdout into (properties, counterexamples, engine_used).

    Conservative: when SBY's output diverges from what we expect, we
    fall back to reporting whatever properties / cex paths we DID see
    and leave the rest empty rather than crashing.
    """
    properties: dict[str, str] = {}
    cex: list[dict[str, Any]] = []
    engine_used: str | None = None

    # Engine identification: SBY emits the engine name in parens after
    # the engine_N id in several places. The exact wording varies by SBY
    # version — "starting process", "returned pass", "returned FAIL" all
    # appear. Match any occurrence of `engine_N (NAME)` and take the first.
    engine_id_re = re.compile(
        r"engine_(\d+)\s*\(([^)]+)\)", re.IGNORECASE
    )
    m = engine_id_re.search(stdout)
    if m:
        engine_used = m.group(2).strip()

    # Per-property results: walk every "Assert failed" hit; default
    # everything not explicitly failed to PASS only after we see a
    # top-level DONE(PASS) signal. Capture each match's end offset so
    # depth_hit extraction sees only the log slice up to and including
    # that assertion's line — keeps multi-failure runs from cross-talking.
    failed_props_seen: list[dict[str, Any]] = []
    for am in _SBY_ASSERT_FAILED_RE.finditer(stdout):
        name = am.group("name") or f"{am.group('module')}@{am.group('file')}:{am.group('line')}"
        failed_props_seen.append({
            "name": name,
            "file": am.group("file"),
            "line": am.group("line"),
            "depth_hit": _extract_depth_hit(stdout[: am.end()]),
        })
        properties[name] = "FAIL"

    # Trace files: associate each trace with the most recently seen
    # failed property (SBY emits them in order, one per failure).
    trace_paths: list[str] = []
    for tm in _SBY_TRACE_RE.finditer(stdout):
        trace_paths.append(tm.group("path"))
    for i, tp in enumerate(trace_paths):
        if i < len(failed_props_seen):
            cex.append({
                "property": failed_props_seen[i]["name"],
                "trace": str(work_dir / tp) if not Path(tp).is_absolute() else tp,
                "depth_hit": failed_props_seen[i]["depth_hit"],
            })

    # Top-level verdict — affects how we backfill the no-explicit-result properties.
    # SBY can finish with DONE(PASS|FAIL|UNKNOWN) without ever printing per-
    # property lines (small designs, cover mode, etc.). The envelope contract
    # promises `properties` is non-empty whenever a verdict was reached, so
    # we synthesize "<all>" entries to keep `summary` and `status` consistent.
    done_match = _SBY_DONE_RE.search(stdout)
    if done_match and not properties:
        verdict = done_match.group("verdict").upper()
        if verdict == "PASS":
            properties["<all>"] = "PASS"
        elif verdict == "UNKNOWN":
            # Without this, status=fail + unknown=0 + pass=0 + fail=0 in summary
            # looks broken to the agent reading the envelope.
            properties["<all>"] = "UNKNOWN"
        elif verdict == "FAIL":
            # Unusual — FAIL with no Assert markers means SBY's parser had no
            # finer-grained source location. Record the verdict anyway.
            properties["<all>"] = "FAIL"

    return properties, cex, engine_used


def _run_sby_backend(
    cfg: dict,
    formal_cfg: dict,
    binary: str,
    print_cmd: bool,
) -> dict:
    root: Path = cfg["_root"]
    proj = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    build_dir = root / proj.get("build_dir", "build")
    work_dir = build_dir / "formal"

    top = formal_cfg.get("top") or proj.get("top")
    if not top:
        return _blocked(
            "[formal].top (or [project].top) is required; specify the "
            "module to prove."
        )

    src_files = _resolve_sources(cfg)
    if not src_files:
        return _blocked(
            "[project].src resolved to zero Verilog/SystemVerilog files; "
            "formal needs at least one source."
        )

    sby_text = _render_sby(formal_cfg, top, src_files, work_dir)
    sby_path = work_dir / "logicpilot_formal.sby"

    cmd = [binary, "-f", str(sby_path)]
    if print_cmd:
        return {
            "stage": "formal",
            "status": "dry-run",
            "tool": "sby",
            "mode": str(formal_cfg.get("mode", "prove")).lower(),
            "depth": int(formal_cfg.get("depth", 20)),
            "cmd": " ".join(cmd),
            "sby_config_preview": sby_text,
        }

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        sby_path.write_text(sby_text)
    except OSError as exc:
        return _blocked(f"cannot write SBY config: {exc}")

    timeout_s = int(formal_cfg.get("timeout_s") or _DEFAULT_TIMEOUT_S)
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            text=True,
            capture_output=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {
            "stage": "formal",
            "status": "timeout",
            "tool": "sby",
            "elapsed_s": round(time.time() - start, 2),
            "cmd": " ".join(cmd),
            "tail": f"sby timed out after {timeout_s}s; raise [formal].timeout_s or trim depth",
            "warnings": [f"stage timed out after {timeout_s} seconds"],
        }

    elapsed = round(time.time() - start, 2)
    out_text = (proc.stdout or "") + (proc.stderr or "")
    properties, cex, engine_used = _parse_sby_output(out_text, work_dir)

    # [formal].properties scoping: if the user opts into a subset, drop
    # everything else and warn about any names they asked for that didn't
    # appear in the SBY log. Empty / missing list = run everything.
    # Defensive: TOML allows int / bool / dict here too — coerce string
    # to list, reject everything else as "no scope" so an int/dict typo
    # doesn't crash the run.
    requested = formal_cfg.get("properties") or []
    if isinstance(requested, str):
        requested = [requested]
    elif not isinstance(requested, list):
        requested = []
    scoping_warnings: list[str] = []
    if requested:
        requested_set = {str(p) for p in requested}
        # `<all>` is the synthetic catch-all; if the user asked for specific
        # names, hide it — they're opting into per-property granularity.
        properties = {
            k: v for k, v in properties.items()
            if k in requested_set
        }
        cex = [c for c in cex if c.get("property") in requested_set]
        missing = sorted(requested_set - set(properties.keys()))
        for m in missing:
            scoping_warnings.append(
                f"[formal].properties requested '{m}' but SBY log had no "
                "matching assertion — check the assertion name or remove it."
            )

    summary = {"pass": 0, "fail": 0, "unknown": 0}
    for v in properties.values():
        if v == "PASS":
            summary["pass"] += 1
        elif v == "FAIL":
            summary["fail"] += 1
        else:
            summary["unknown"] += 1

    # Status calculation: when the user scoped to specific properties, the
    # filtered summary becomes authoritative (a global DONE(PASS) doesn't
    # mean their property exists). Otherwise the explicit DONE marker wins.
    done_match = _SBY_DONE_RE.search(out_text)
    if requested:
        if summary["fail"] or summary["unknown"]:
            status = "fail"
        elif summary["pass"]:
            status = "pass"
        else:
            # Asked-for properties missing entirely — treat as fail so the
            # caller doesn't ship on an empty proof.
            status = "fail"
    elif done_match:
        v = done_match.group("verdict").upper()
        status = {"PASS": "pass", "FAIL": "fail", "UNKNOWN": "fail"}[v]
    elif proc.returncode == 0:
        status = "pass"
    else:
        status = "fail"

    result: dict[str, Any] = {
        "stage": "formal",
        "status": status,
        "tool": "sby",
        "mode": str(formal_cfg.get("mode", "prove")).lower(),
        "depth": int(formal_cfg.get("depth", 20)),
        "engine_used": engine_used,
        "properties": properties,
        "counterexamples": cex,
        "summary": summary,
        "returncode": proc.returncode,
        "elapsed_s": elapsed,
        "cmd": " ".join(cmd),
        "tail": "\n".join(out_text.splitlines()[-25:]) or "sby produced no output",
    }
    if requested:
        result["requested_properties"] = sorted(requested_set)
    for w in scoping_warnings:
        result.setdefault("warnings", []).append(w)
    if status != "pass":
        result.setdefault("warnings", []).append(
            f"formal stage status={status}: "
            f"{summary['fail']} FAIL, {summary['unknown']} UNKNOWN. "
            "Read 'counterexamples' for trace VCD paths."
        )
    return result


# --- Commercial-tool stubs -------------------------------------------------

def _commercial_stub(tool_name: str) -> dict:
    """Common stub for jaspergold / vcf / qverify backends."""
    return {
        "stage": "formal",
        "status": "blocked",
        "tool": tool_name,
        "reason": (
            f"LogicPilot detected {tool_name} on PATH and dispatched, but "
            "the vendor-specific output parser is not yet implemented. "
            "The envelope shape (mode / depth / properties / "
            "counterexamples / summary) is frozen — file an issue with "
            "an anonymized session log and the parser can be added "
            "without breaking the contract. To use SBY instead, set "
            "`[formal].backend = \"sby\"` (requires sby + yosys)."
        ),
        "tail": (
            f"backend={tool_name} dispatched, no parser yet. "
            "See https://github.com/shijhtop/LogicPilot/issues to contribute one."
        ),
    }


# --- Entry point -----------------------------------------------------------

def run_formal(
    cfg: dict,
    *,
    print_cmd: bool = False,
    experimental: set[str] | None = None,
) -> dict:
    """Top-level dispatch. ``experimental={"formal"}`` is required."""
    experimental = experimental or set()
    if "formal" not in experimental:
        return _blocked(
            "formal stage is gated behind --experimental-formal. "
            "Re-run with `--experimental-formal` (or export "
            "LOGICPILOT_EXPERIMENTAL_FORMAL=1) to opt in. The flag is "
            "in preview — envelope is frozen but rule set may evolve "
            "between minor versions."
        )

    formal_cfg = _formal_cfg(cfg)
    backend, binary = _pick_backend(formal_cfg)
    if not backend:
        # If the user pinned a specific backend, report that one as missing.
        pinned = formal_cfg.get("backend")
        if isinstance(pinned, str) and pinned:
            return _blocked(
                f"pinned backend '{pinned}' not on PATH",
                missing_tools=[_probe_for(pinned)],
            )
        missing = [probe for _name, probe in _BACKEND_PROBES]
        return _blocked(
            "no formal backend installed (looked for: " + ", ".join(missing) + ")",
            missing_tools=missing,
        )

    if backend == "sby":
        return _run_sby_backend(cfg, formal_cfg, binary, print_cmd)
    # Commercial backends — print dry-run cmd if requested, otherwise stub.
    if print_cmd:
        return {
            "stage": "formal",
            "status": "dry-run",
            "tool": backend,
            "mode": str(formal_cfg.get("mode", "prove")).lower(),
            "depth": int(formal_cfg.get("depth", 20)),
            "cmd": f"<vendor parser not yet implemented for {backend}>",
        }
    return _commercial_stub(backend)


def _probe_for(backend_name: str) -> str:
    for name, probe in _BACKEND_PROBES:
        if name == backend_name:
            return probe
    return backend_name
