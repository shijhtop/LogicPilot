"""Power analysis — VCS SAIF (if available) → Vivado report_power.

SAIF source priority:
  1. [activity].saif_file in flow.toml — user-provided, used as-is.
  2. vcs on PATH — SAIF generated directly from simulation.
  3. Neither — vectorless estimate only.

VCD is not used. Vectorless is an acceptable fallback for early exploration
but must be disclosed in the assumptions field.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .diagnostics import power_assumptions, power_warnings
from .install_hints import hints_for
from .metrics import parse_metrics
from .variables import build_vars, render


def run_power(cfg: dict, *, print_cmd: bool = False) -> dict:
    base = {"stage": "power"}
    variables = build_vars(cfg)

    if not shutil.which("vivado"):
        return {
            **base,
            "status": "blocked",
            "reason": "Vivado not found — power analysis requires Vivado report_power",
            "missing": ["vivado"],
            "install_hint": hints_for(["vivado"]),
        }

    root: Path = cfg["_root"]
    build_dir = Path(render("{build}", variables))
    dcp = build_dir / f"{variables['top']}_impl.dcp"
    if not dcp.exists():
        return {
            **base,
            "status": "blocked",
            "reason": f"implementation checkpoint not found: {dcp} — run pnr first",
            "missing_paths": [str(dcp)],
        }

    build_dir.mkdir(parents=True, exist_ok=True)
    saif_out = build_dir / "power.saif"

    # SAIF source resolution
    user_saif = variables.get("saif_file", "")
    if user_saif:
        saif_path: Path | None = Path(user_saif)
        saif_source = f"saif:{saif_path}"
    elif shutil.which("vcs"):
        vcs_cmd = _vcs_saif_cmd(variables)
        if print_cmd:
            return {
                **base,
                "status": "dry-run",
                "tool": "vcs+vivado",
                "vcs_cmd": vcs_cmd,
                "note": "VCS generates SAIF; Vivado reads SAIF for annotated power",
            }
        proc = subprocess.run(
            vcs_cmd, shell=True, cwd=root, text=True, capture_output=True,
        )
        if proc.returncode == 0 and saif_out.exists():
            saif_path = saif_out
            saif_source = f"saif:{saif_path}"
        else:
            saif_path = None
            saif_source = "vectorless (vcs run failed)"
    else:
        saif_path = None
        saif_source = "vectorless (vcs not found)"

    if print_cmd:
        tcl = _vivado_tcl(variables, saif_path)
        return {
            **base,
            "status": "dry-run",
            "tool": "vivado",
            "activity": saif_source,
            "tcl": tcl,
        }

    tcl = _vivado_tcl(variables, saif_path)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tcl", delete=False) as f:
        f.write(tcl)
        tcl_file = f.name

    vivado_cmd = f"vivado -mode batch -nojournal -nolog -source {tcl_file}"
    start = time.time()
    try:
        proc = subprocess.run(
            vivado_cmd, shell=True, cwd=root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=1200,
        )
        elapsed = round(time.time() - start, 2)
        log_text = proc.stdout or ""
        status = "pass" if proc.returncode == 0 else "fail"
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.time() - start, 2)
        log_text = getattr(exc, "output", "") or ""
        status = "timeout"
    finally:
        Path(tcl_file).unlink(missing_ok=True)

    metrics = parse_metrics(log_text, cfg, stage_name="power")
    assumptions = power_assumptions(log_text, cfg, variables)
    warnings = power_warnings(log_text, metrics, cfg)

    result: dict = {
        **base,
        "status": status,
        "tool": "vivado",
        "activity": saif_source,
        "assumptions": assumptions,
        "metrics": metrics,
        "elapsed_s": elapsed,
        "tail": "\n".join(log_text.splitlines()[-25:]),
    }
    if warnings:
        result["warnings"] = warnings
    return result


def _vcs_saif_cmd(variables: dict) -> str:
    return render(
        "vcs -full64 -sverilog {src} {tb} -o {build}/simv_power && "
        "{build}/simv_power +saif=on +saif_file={build}/power.saif +saif_scope={tb_top}",
        variables,
    )


def _vivado_tcl(variables: dict, saif_path: Path | None) -> str:
    lines = [f"open_checkpoint {variables['build']}/{variables['top']}_impl.dcp"]
    if saif_path and Path(saif_path).exists():
        lines += [
            f"read_saif -input {saif_path}",
            f'puts "POWER_ACTIVITY: SAIF {saif_path}"',
        ]
    else:
        lines.append('puts {POWER_ACTIVITY: vectorless/default switching activity}')
    lines += [
        f"report_power -file {variables['build']}/power_impl.rpt",
        'puts "== power =="',
        f"puts [exec cat {variables['build']}/power_impl.rpt]",
    ]
    return "\n".join(lines)
