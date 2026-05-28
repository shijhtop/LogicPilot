"""LogicPilot hardware flow internals."""
from __future__ import annotations


import subprocess
import time
from pathlib import Path

from .audit import run_source_audit, run_testbench_audit
from .cdc_check import run_cdc_check
from .diagnostics import (
    quality_warnings,
    sim_walltime_warnings,
    verification_failures,
    verification_warnings,
)
from .install_hints import hints_for
from .metrics import evaluate_checks, parse_metrics
from .constraints_gen import run_constraints
from .formal import run_formal
from .plan_check import run_plan_check
from .power import run_power
from .report import run_report
from . import scheduler as _scheduler
from .stages import BUILTIN_STAGES, STAGE_ORDER, resolve_stage
from .utils import _coerce_timeout, _timeout_output
from .variables import build_vars, render

def run_stage(
    name: str,
    cfg: dict,
    *,
    print_cmd: bool = False,
    soft_mode: bool = False,
    experimental: set[str] | None = None,
) -> dict:
    """Run a single stage. ``soft_mode`` is passed through to plan-check
    only; for every other stage it is ignored. Direct callers default to
    hard mode (existing behavior); ``run_all`` flips it to soft for the
    v0.6 deprecation cycle.

    ``experimental`` carries the active ``--experimental-*`` feature
    names (see ``features.py``). Stages that recognize a flag opt in to
    new behaviour; stages that don't ignore it. Default ``None`` is
    equivalent to "no experimental flags active" — keeps every existing
    test / caller working without modification.
    """
    experimental = experimental or set()
    if name == "plan-check":
        return run_plan_check(cfg, print_cmd=print_cmd, soft_mode=soft_mode)
    if name == "audit":
        return run_source_audit(cfg, print_cmd=print_cmd, experimental=experimental)
    if name == "tb-audit":
        return run_testbench_audit(cfg, print_cmd=print_cmd)
    if name == "cdc-check":
        return run_cdc_check(cfg, print_cmd=print_cmd, experimental=experimental)
    if name == "power":
        return run_power(cfg, print_cmd=print_cmd)
    if name == "constraints":
        return run_constraints(cfg, print_cmd=print_cmd)
    if name == "formal":
        return run_formal(cfg, print_cmd=print_cmd, experimental=experimental)
    if name == "report":
        return run_report(cfg, print_cmd=print_cmd)

    stages = cfg["_stages"]
    if name not in stages:
        return {"stage": name, "status": "skipped", "reason": "not defined in config"}

    resolved = resolve_stage(name, cfg)
    if "blocked" in resolved:
        out = {
            "stage": name, "status": "blocked", "hdl": resolved["hdl"],
            "reason": resolved["blocked"], "candidates": resolved.get("candidates", []),
        }
        if resolved.get("command_source"):
            out["command_source"] = resolved["command_source"]
        if resolved.get("missing"):
            out["missing"] = resolved["missing"]
            # v0.7a §4a.3: attach install_hint when we know how to install
            # the missing tool. Silently omit if no hint is registered
            # (additive evolution — empty hint is worse than no hint).
            hints = hints_for(resolved["missing"])
            if hints:
                out["install_hint"] = hints
        if resolved.get("missing_paths"):
            out["missing_paths"] = resolved["missing_paths"]
        return out

    variables = build_vars(cfg)
    cmd = render(resolved["cmd"], variables)
    tool, hdl = resolved.get("tool"), resolved.get("hdl")
    command_source = resolved.get("command_source", "project_config")
    timeout_s = _coerce_timeout(resolved.get("timeout_s"))

    root: Path = cfg["_root"]
    log_dir = Path(variables["build"]) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{name}.log"

    if print_cmd:
        return {
            "stage": name, "status": "dry-run", "hdl": hdl, "tool": tool,
            "command_source": command_source,
            "probes": resolved.get("probes", []),
            "timeout_s": timeout_s,
            "cmd": cmd,
        }

    start = time.time()
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=root, text=True, timeout=timeout_s,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        elapsed = round(time.time() - start, 2)
        log_text = proc.stdout or ""
        log_file.write_text(log_text)
        status = "pass" if proc.returncode == 0 else "fail"
        returncode = proc.returncode
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.time() - start, 2)
        log_text = _timeout_output(exc)
        log_file.write_text(log_text)
        status = "timeout"
        returncode = None

    metrics = parse_metrics(log_text, cfg, stage_name=name)
    checks_result = evaluate_checks(log_text, resolved.get("checks"))

    result = {
        "stage": name,
        "status": status,
        "hdl": hdl,
        "tool": tool,
        "command_source": command_source,
        "probes": resolved.get("probes", []),
        "returncode": returncode,
        "elapsed_s": elapsed,
        "timeout_s": timeout_s,
        "log": str(log_file),
        "metrics": metrics,
        "tail": "\n".join(log_text.splitlines()[-25:]),
    }

    if name in ("sim", "verify", "coverage"):
        verification_flags = verification_warnings(log_text, metrics, cfg)
        if verification_flags:
            result.setdefault("warnings", []).extend(verification_flags)
        # v0.7b §4b.2 #3: wall-clock heuristic. Pass log_text so the
        # LOGICPILOT_SEED marker can short-circuit the warning when the
        # TB clearly DID run (fast open-source simulators land here).
        wall_flags = sim_walltime_warnings(elapsed, metrics, log_text)
        if wall_flags:
            result.setdefault("warnings", []).extend(wall_flags)
        # v0.7b §4b.3: opt-in hard gate. require_seed_log=true with
        # randomized test but no LOGICPILOT_SEED marker → fail.
        hard_fails = verification_failures(log_text, metrics, cfg)
        if hard_fails:
            result["status"] = "fail"
            result.setdefault("warnings", []).extend(hard_fails)

    if checks_result:
        result["checks"] = checks_result
        if checks_result.get("status") == "fail":
            result["status"] = "fail"
            result.setdefault("warnings", []).append(
                "stage output checks failed: " + ", ".join(checks_result.get("reasons", []))
            )

    if status == "timeout":
        result.setdefault("warnings", []).append(f"stage timed out after {timeout_s} seconds")
        return result

    # Flag timing failure even when the tool exits 0 (common with nextpnr).
    wns = result["metrics"].get("wns_ns")
    if isinstance(wns, (int, float)) and wns < 0:
        result.setdefault("warnings", []).append(f"timing not met: WNS={wns} ns")
    # Elevate synthesis red flags (latch/multi-driver) so the agent sees them
    # even on a returncode-0 run instead of having to scan the full log.
    flags = quality_warnings(log_text)
    if flags:
        result.setdefault("warnings", []).extend(flags)
    return result

def run_all(
    cfg: dict,
    *,
    print_cmd: bool = False,
    no_plan_gate: bool = False,
    strict_plan: bool = False,
    experimental: set[str] | None = None,
    jobs: int = 1,
) -> dict:
    """Run the full pipeline.

    v0.6 deprecation cycle controls (apply only to the plan-check stage):

    - ``no_plan_gate=True``: remove plan-check from the pipeline entirely
      (escape hatch matching the v0.5.x behavior).
    - ``strict_plan=True``: run plan-check in hard-fail mode (preview the
      v0.7b behavior). Default is soft mode — would-be failures become
      pass + prefixed warnings + a deprecation field.

    ``jobs`` (post-v1.0, additive):
    - ``jobs == 1`` (default): byte-identical to the pre-scheduler
      sequential loop. Preserves every existing CI integration.
    - ``jobs > 1``: dispatch to ``scheduler.run_dag`` honoring
      ``[stages.<name>].depends_on`` declarations and the resource
      hints (expected_mem_gb / expected_cpu_cores / license_token).
      Stages without ``depends_on`` fall back to the original
      sequential order as their implicit predecessor chain — the
      first stage in ``order`` has no predecessors, every subsequent
      stage depends on the previous one. This means a project with no
      DAG declarations still runs sequentially under ``--jobs N``.

    All other stages run identically regardless of these flags.
    """
    stages = cfg["_stages"]
    # The built-in audit/tb-audit/report run with no external tool, so they are
    # always eligible for `all` even though they are not declared in _stages.
    # A project/preset can drop them with [pipeline] skip_builtin = true.
    include_builtin = not cfg.get("pipeline", {}).get("skip_builtin", False)

    def _available(name: str) -> bool:
        return name in stages or (include_builtin and name in BUILTIN_STAGES)

    declared = cfg.get("_pipeline") or []
    base = declared if declared else STAGE_ORDER
    order = [s for s in base if _available(s)]
    # When the project explicitly declared `[pipeline].order`, treat it
    # as authoritative — DON'T silently append every preset-defined
    # stage. The user said "run exactly these". Built-ins still get
    # injected below for safety. When the project did NOT declare an
    # order, fall back to the historical "STAGE_ORDER + any defined
    # extras" behaviour so legacy projects keep working.
    if not declared:
        order += [s for s in stages if s not in order]

    if include_builtin:
        # Inject any front-end gate / summary the chosen order forgot, in the
        # canonical place: audit + tb-audit before everything else, report last.
        # An explicitly declared pipeline that DOES list them keeps its own
        # placement (they are already in `order` and won't be re-inserted).
        if "tb-audit" not in order:
            order.insert(0, "tb-audit")
        if "audit" not in order:
            order.insert(0, "audit")
        if "report" not in order:
            order.append("report")

    # v0.6 escape hatch: --no-plan-gate removes plan-check entirely.
    if no_plan_gate:
        order = [s for s in order if s != "plan-check"]

    # v0.7b: plan-check is now hard-fail by default (the v0.6→v0.7b
    # deprecation cycle is complete). The strict_plan flag and the
    # LOGICPILOT_STRICT env var are kept as accepted-but-no-op aliases
    # so CI pipelines that adopted them during the v0.6 deprecation
    # window keep working unchanged. --no-plan-gate is still the
    # escape hatch for matching v0.5.x behavior.
    plan_soft_mode = False

    experimental = experimental or set()

    if jobs > 1:
        return _run_all_parallel(
            cfg, order, jobs=jobs, print_cmd=print_cmd,
            plan_soft_mode=plan_soft_mode, experimental=experimental,
        )

    results = []
    for name in order:
        if name == "plan-check":
            r = run_stage(
                name, cfg, print_cmd=print_cmd, soft_mode=plan_soft_mode,
                experimental=experimental,
            )
        else:
            r = run_stage(
                name, cfg, print_cmd=print_cmd, experimental=experimental,
            )
        results.append(r)
        if r.get("status") in ("fail", "blocked", "timeout"):
            r.setdefault("warnings", []).append("pipeline halted at this stage")
            break
    statuses = [r.get("status") for r in results]
    if "fail" in statuses:
        overall = "fail"
    elif "timeout" in statuses:
        overall = "timeout"
    elif "blocked" in statuses:
        overall = "blocked"   # halted on a missing tool, not a design defect
    else:
        overall = "pass"
    return {"pipeline": order, "overall": overall, "results": results}


def _build_depends_on(cfg: dict, order: list[str]) -> dict[str, list[str]]:
    """Build the ``depends_on`` map fed to the scheduler.

    Two sources merged in order of precedence (later wins):
    1. Implicit sequential chain — every stage depends on the previous
       one in ``order``. Guarantees an undeclared project still runs
       sequentially under ``--jobs N``.
    2. Explicit ``[stages.<name>].depends_on`` lists from flow.toml —
       REPLACES the implicit predecessor for that stage. Lets a
       project mark stages as truly independent.
    """
    deps: dict[str, list[str]] = {}
    prev: str | None = None
    stage_specs = cfg.get("_stages", {})
    for name in order:
        spec = stage_specs.get(name)
        explicit = (
            spec.get("depends_on") if isinstance(spec, dict) else None
        )
        if isinstance(explicit, list) and all(isinstance(x, str) for x in explicit):
            deps[name] = [d for d in explicit if d in order]
        elif prev is not None:
            deps[name] = [prev]
        prev = name
    return deps


def _build_hints(cfg: dict, order: list[str]) -> dict[str, _scheduler.ResourceHints]:
    """Materialize the per-stage resource hints fed to the scheduler.

    Built-in stages (audit, tb-audit, plan-check, cdc-check, report)
    have no flow.toml spec and therefore no hints — they get the
    no-constraint defaults, which is the right call because they're
    cheap.
    """
    out: dict[str, _scheduler.ResourceHints] = {}
    for name in order:
        spec = cfg.get("_stages", {}).get(name)
        out[name] = _scheduler.hints_from_spec(spec) if spec else _scheduler.ResourceHints()
    return out


def _run_all_parallel(
    cfg: dict,
    order: list[str],
    *,
    jobs: int,
    print_cmd: bool,
    plan_soft_mode: bool,
    experimental: set[str],
) -> dict:
    """Parallel path. Wraps scheduler.run_dag with a per-stage runner.

    On cycle detection: falls back to sequential with a warning row.
    Preserves the JSON envelope shape — adds a ``scheduler`` object
    with telemetry plus the result list re-sorted into declared
    pipeline order so consumers don't have to handle a new ordering
    surprise.
    """
    deps = _build_depends_on(cfg, order)
    cycle = _scheduler.find_cycle(order, deps)
    if cycle is not None:
        # Run sequentially; surface the cycle as a top-level warning.
        seq = run_all(
            cfg, print_cmd=print_cmd, no_plan_gate=False,
            strict_plan=False, experimental=experimental, jobs=1,
        )
        seq.setdefault("warnings", []).append(
            f"depends_on cycle detected ({' -> '.join(cycle)}); "
            "ignored --jobs and ran sequentially"
        )
        seq["scheduler"] = {"jobs": jobs, "fell_back_to_sequential": True,
                            "cycle": cycle}
        return seq

    hints = _build_hints(cfg, order)

    def _runner(name: str) -> dict:
        if name == "plan-check":
            return run_stage(
                name, cfg, print_cmd=print_cmd, soft_mode=plan_soft_mode,
                experimental=experimental,
            )
        return run_stage(
            name, cfg, print_cmd=print_cmd, experimental=experimental,
        )

    completion_order, telemetry = _scheduler.run_dag(
        order, deps, hints, _runner, jobs=jobs, halt_on_failure=True,
    )

    # Re-sort results back into declared pipeline order for the JSON
    # envelope. Stages that were halted (never ran) are omitted —
    # matches sequential-mode behavior where the loop break left them
    # off the result list.
    by_name = {r.get("stage"): r for r in completion_order}
    results = [by_name[s] for s in order if s in by_name]

    # Mark the boundary stage so the user can see where halting kicked in,
    # mirroring the sequential path's "pipeline halted at this stage" warning.
    if any(r.get("status") in ("fail", "blocked", "timeout") for r in results):
        # Find the first non-pass in completion order — that's the boundary.
        for r in completion_order:
            if r.get("status") in ("fail", "blocked", "timeout"):
                r.setdefault("warnings", []).append("pipeline halted at this stage")
                break

    statuses = [r.get("status") for r in results]
    if "fail" in statuses:
        overall = "fail"
    elif "timeout" in statuses:
        overall = "timeout"
    elif "blocked" in statuses:
        overall = "blocked"
    else:
        overall = "pass"

    return {
        "pipeline": order,
        "overall": overall,
        "results": results,
        "scheduler": telemetry,
    }
