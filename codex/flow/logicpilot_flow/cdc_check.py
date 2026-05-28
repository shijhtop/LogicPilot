"""Built-in cdc-check stage: SpyGlass CDC → Verilator --cdc fallback.

Clock detection (determines whether to run at all):
  1. [cdc].clocks list in flow.toml — explicit, authoritative.
  2. RTL scan: collect unique names from posedge/negedge sensitivity lists.
  If ≤1 distinct clock is found the stage returns status="skip".

Tool priority:
  sg_shell (SpyGlass CDC) → verilator (--cdc mode)
  If neither is installed: status="blocked" with install_hint.

SpyGlass script:
  Set [cdc].spyglass_script in flow.toml to point at a project TCL script.
  Without it, a minimal inline TCL is used (suitable for small designs only).

JSON envelope fields: stage, status, tool, clocks,
  violations_total, violations, tail, log (when a tool ran).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from .config import _expand_globs
from .install_hints import hints_for
from .variables import build_vars

_RTL_EXTS = {".v", ".vh", ".sv", ".svh"}

# Matches posedge/negedge clock names in sensitivity lists.
_CLOCK_PAT = re.compile(r"@\s*\(\s*(?:posedge|negedge)\s+(\w+)", re.I)

# Verilator --cdc warning lines:
#   %Warning-CDCRSTLOGIC: file.sv:42:5: message
_VLT_CDC_PAT = re.compile(
    r"%Warning-CDC(\w+):\s*([^:]+):(\d+):\d+:\s*(.*)", re.I
)

# SpyGlass CDC violation table rows:
#   Ac_unsync01  | Error  | Active | top.u_sync.q | ...message...
_SG_VIOLATION_PAT = re.compile(
    r"^((?:Ac|Cdc|Waivers)_\w+)\s*\|\s*(\w+)\s*\|[^|]*\|[^|]*\|\s*(.*)",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Clock detection
# ---------------------------------------------------------------------------

def _iter_rtl_sources(cfg: dict) -> list[Path]:
    root: Path = cfg["_root"]
    proj = cfg.get("project") or {}
    patterns = proj.get("src_ordered", proj.get("src", []))
    files = []
    for f in _expand_globs(patterns, root):
        p = Path(f) if Path(f).is_absolute() else root / f
        if p.exists() and p.suffix.lower() in _RTL_EXTS:
            files.append(p.resolve())
    seen, out = set(), []
    for p in files:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def _scan_rtl_clocks(cfg: dict) -> list[str]:
    clocks: set[str] = set()
    for src in _iter_rtl_sources(cfg):
        try:
            text = src.read_text(errors="replace")
        except OSError:
            continue
        for m in _CLOCK_PAT.finditer(text):
            clocks.add(m.group(1))
    return sorted(clocks)


def _detect_clocks(cfg: dict) -> list[str]:
    """Return clock list from [cdc].clocks or RTL scan."""
    cdc_cfg = cfg.get("cdc") or {}
    declared = cdc_cfg.get("clocks") or []
    if isinstance(declared, list) and declared:
        return [str(c) for c in declared]
    return _scan_rtl_clocks(cfg)


# ---------------------------------------------------------------------------
# Tool execution helper
# ---------------------------------------------------------------------------

def _run_tool(
    cmd: str, cwd: Path, timeout_s: float, log_file: Path
) -> tuple[str, int | None, float, str]:
    start = time.time()
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=cwd, text=True, timeout=timeout_s,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        elapsed = round(time.time() - start, 2)
        log_text = proc.stdout or ""
        log_file.write_text(log_text)
        status = "pass" if proc.returncode == 0 else "fail"
        return log_text, proc.returncode, elapsed, status
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.time() - start, 2)
        partial = exc.output or b""
        log_text = f"timed out after {timeout_s}s\n"
        if partial:
            log_text += partial if isinstance(partial, str) else partial.decode(errors="replace")
        log_file.write_text(log_text)
        return log_text, None, elapsed, "timeout"


def _log_dir(cfg: dict) -> Path:
    variables = build_vars(cfg)
    root: Path = cfg["_root"]
    build = variables.get("build", "build")
    d = Path(build) if Path(build).is_absolute() else root / build
    log_d = d / "logs"
    log_d.mkdir(parents=True, exist_ok=True)
    return log_d


# ---------------------------------------------------------------------------
# Verilator --cdc
# ---------------------------------------------------------------------------

def _parse_verilator_cdc(log: str) -> list[dict]:
    violations = []
    for m in _VLT_CDC_PAT.finditer(log):
        violations.append({
            "rule": f"CDC{m.group(1)}",
            "file": m.group(2).strip(),
            "line": int(m.group(3)),
            "message": m.group(4).strip(),
            "severity": "high",
        })
    return violations


def _run_verilator_cdc(cfg: dict, clocks: list[str], print_cmd: bool) -> dict:
    variables = build_vars(cfg)
    root: Path = cfg["_root"]
    top = variables.get("top_module", "")
    src = variables.get("src", "")
    log_file = _log_dir(cfg) / "cdc-check.log"

    top_flag = f"--top-module {top}" if top else ""
    cmd = f"verilator --cdc -sv {top_flag} {src} 2>&1"

    if print_cmd:
        return {
            "stage": "cdc-check", "status": "dry-run",
            "tool": "verilator", "clocks": clocks, "cmd": cmd,
        }

    log_text, rc, elapsed, status = _run_tool(cmd, root, 300.0, log_file)
    violations = _parse_verilator_cdc(log_text)
    if violations and status == "pass":
        status = "fail"

    result: dict = {
        "stage": "cdc-check",
        "status": status,
        "tool": "verilator",
        "clocks": clocks,
        "returncode": rc,
        "elapsed_s": elapsed,
        "log": str(log_file),
        "violations_total": len(violations),
        "violations": violations,
        "tail": "\n".join(log_text.splitlines()[-25:]),
    }
    if status == "fail" and not violations:
        result.setdefault("warnings", []).append(
            "verilator exited non-zero but no CDC warnings were parsed; "
            "check the log for compilation errors"
        )
    return result


# ---------------------------------------------------------------------------
# SpyGlass CDC
# ---------------------------------------------------------------------------

def _parse_spyglass_cdc(log: str) -> list[dict]:
    violations = []
    for m in _SG_VIOLATION_PAT.finditer(log):
        sev_raw = m.group(2).strip().lower()
        sev = "high" if sev_raw in ("error", "fatal") else "medium"
        violations.append({
            "rule": m.group(1).strip(),
            "severity": sev,
            "message": m.group(3).strip(),
        })
    return violations


def _run_spyglass_cdc(cfg: dict, clocks: list[str], print_cmd: bool) -> dict:
    variables = build_vars(cfg)
    root: Path = cfg["_root"]
    cdc_cfg = cfg.get("cdc") or {}
    log_dir = _log_dir(cfg)
    log_file = log_dir / "cdc-check.log"

    user_script = cdc_cfg.get("spyglass_script")
    if user_script:
        script_path = Path(user_script)
        if not script_path.is_absolute():
            script_path = root / script_path
        cmd = f"sg_shell -tcl {script_path}"
        used_inline = False
    else:
        top = variables.get("top_module", "")
        src = variables.get("src", "")
        rpt = str(log_dir / "spyglass_cdc.rpt")
        tcl = (
            f"read_file -type verilog {src}; "
            f"set_option -top {top}; "
            f"run_goal cdc/cdc_verify_struct; "
            f"report -type cdc -format text -out {rpt}"
        )
        cmd = f"sg_shell -tcl '{tcl}'"
        used_inline = True

    if print_cmd:
        return {
            "stage": "cdc-check", "status": "dry-run",
            "tool": "spyglass", "clocks": clocks, "cmd": cmd,
        }

    log_text, rc, elapsed, status = _run_tool(cmd, root, 600.0, log_file)
    violations = _parse_spyglass_cdc(log_text)
    if violations and status == "pass":
        status = "fail"

    result: dict = {
        "stage": "cdc-check",
        "status": status,
        "tool": "spyglass",
        "clocks": clocks,
        "returncode": rc,
        "elapsed_s": elapsed,
        "log": str(log_file),
        "violations_total": len(violations),
        "violations": violations,
        "tail": "\n".join(log_text.splitlines()[-25:]),
    }
    if used_inline:
        result.setdefault("warnings", []).append(
            "no [cdc].spyglass_script in flow.toml; used inline TCL. "
            "Set [cdc].spyglass_script = path/to/cdc.tcl for full library/SDC setup."
        )
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_cdc_check(
    cfg: dict,
    *,
    print_cmd: bool = False,
    experimental: set[str] | None = None,
) -> dict:
    clocks = _detect_clocks(cfg)

    if len(clocks) < 2:
        return {
            "stage": "cdc-check",
            "status": "skip",
            "reason": "single-clock design — CDC check not applicable",
            "clocks": clocks,
        }

    if shutil.which("sg_shell"):
        return _run_spyglass_cdc(cfg, clocks, print_cmd)

    if shutil.which("verilator"):
        return _run_verilator_cdc(cfg, clocks, print_cmd)

    return {
        "stage": "cdc-check",
        "status": "blocked",
        "reason": "multi-clock design but no CDC tool installed (sg_shell or verilator)",
        "clocks": clocks,
        "missing": ["sg_shell", "verilator"],
        "install_hint": hints_for(["sg_shell", "verilator"]),
    }
