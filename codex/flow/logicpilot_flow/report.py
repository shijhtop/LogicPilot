"""LogicPilot hardware flow internals."""
from __future__ import annotations


from pathlib import Path

from .diagnostics import power_warnings, quality_warnings, verification_warnings
from .metrics import parse_metrics
from .variables import build_vars

def run_report(cfg: dict, *, print_cmd: bool = False) -> dict:
    """Summarize existing build logs into a machine-readable report."""
    variables = build_vars(cfg)
    root: Path = cfg["_root"]
    log_dir = Path(variables["build"]) / "logs"
    if print_cmd:
        return {"stage": "report", "status": "dry-run", "tool": "built-in-report", "log_dir": str(log_dir)}
    entries = []
    warnings = []
    if not log_dir.exists():
        return {
            "stage": "report",
            "status": "pass",
            "tool": "built-in-report",
            "log_dir": str(log_dir),
            "reports": [],
            "warnings": ["no build/logs directory found; run audit/lint/sim/synth/power first"],
        }
    for log in sorted(log_dir.glob("*.log")):
        try:
            text = log.read_text(errors="ignore")
        except OSError as exc:
            warnings.append(f"could not read {log}: {exc}")
            continue
        stage = log.stem
        # Pass stage_name so parse_metrics enables stage-scoped patterns
        # (in particular, the power-only bare-word regexes — without
        # this, re-reading build/logs/power.log post-hoc returns {}
        # because the power patterns stay disabled).
        metrics = parse_metrics(text, cfg, stage_name=stage)
        flags = []
        if stage in ("synth", "pnr", "gls"):
            flags.extend(quality_warnings(text))
        if stage == "power":
            flags.extend(power_warnings(text, metrics, cfg))
        if stage in ("sim", "verify", "coverage"):
            flags.extend(verification_warnings(text, metrics, cfg))
        entries.append({
            "stage": stage,
            "log": str(log),
            "metrics": metrics,
            "warnings": flags,
            "tail": "\n".join(text.splitlines()[-10:]),
        })
    if not entries:
        warnings.append("no *.log files found in build/logs")
    return {
        "stage": "report",
        "status": "pass",
        "tool": "built-in-report",
        "log_dir": str(log_dir),
        "reports": entries,
        "warnings": warnings,
    }
