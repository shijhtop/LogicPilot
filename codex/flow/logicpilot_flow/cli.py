"""Command-line interface for LogicPilot hardware flow."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import load_config, resolve_hdl, resolve_hdl_info, resolve_hdl_scope, _project_root
from .config_schema import format_errors, validate
from .doctor import run_doctor
from .features import collect_active as collect_experimental
from .features import warnings_for_active as experimental_warnings
from .init import run_init
from .install_hints import hints_for
from .stages import (
    BUILTIN_STAGES_NEEDING_ANY_TOOL,
    BUILTIN_STAGES_NEEDING_TOOL,
    resolve_stage,
)
from .runner import run_all, run_stage
from .tools import discover_tools
from .trust import _project_is_trusted, _trust_file_path
from .utils import _coerce_timeout
from .variables import build_vars

# v0.6 deprecation cycle: LOGICPILOT_STRICT=1 (or true/yes/on, case-insensitive)
# flips plan-check from soft mode (v0.6 default) to hard-fail (v0.7b preview).
# Conservative parser: only well-known truthy tokens count.
_STRICT_TRUTHY = {"1", "true", "yes", "on"}


def _strict_plan_from_env() -> bool:
    """Return True iff LOGICPILOT_STRICT env var is set to a truthy value."""
    raw = os.environ.get("LOGICPILOT_STRICT", "").strip().lower()
    return raw in _STRICT_TRUTHY

def main(argv=None) -> int:
    # v0.10 §7.2.3: strip --experimental-* flags before argparse sees them
    # (argparse otherwise rejects unknown options). Unknown experimental
    # flags pass through so argparse can produce a normal error.
    import sys as _sys
    raw_argv = list(argv if argv is not None else _sys.argv[1:])
    active_experimental, raw_argv = collect_experimental(raw_argv)
    argv = raw_argv

    p = argparse.ArgumentParser(description="Toolchain-agnostic hardware flow driver")
    p.add_argument("stage", nargs="?", help="stage name, or 'all'")
    p.add_argument("--config", default="flow.toml")
    p.add_argument("--list", action="store_true", help="list stages and exit")
    p.add_argument("--tools", action="store_true", help="detect available EDA tools and stage readiness")
    p.add_argument("--doctor", action="store_true",
                   help="run the project + machine health check (answers 'can I run this?')")
    p.add_argument("--init", action="store_true",
                   help="scaffold a new LogicPilot project in the current directory")
    p.add_argument("--with-templates", action="store_true",
                   help="(--init) also generate docs/{spec,uarch,plan}.md with <<FILL:>> placeholders")
    p.add_argument("--non-interactive", action="store_true",
                   help="(--init) skip stdin prompts; use defaults for missing fields")
    p.add_argument("--hdl", choices=["verilog", "systemverilog", "vhdl", "mixed"],
                   help="(--init) HDL family")
    p.add_argument("--target", choices=["open-fpga", "vivado", "openlane", "front-only"],
                   help="(--init) target platform")
    p.add_argument("--scope", choices=["block", "project"],
                   help="(--init) project scope")
    p.add_argument("--top", help="(--init) top-level module name")
    p.add_argument("--print-cmd", action="store_true", help="show resolved command, don't run")
    p.add_argument("--safe-preset-only", action="store_true",
                   help="ignore project-local presets/stages; only run shipped preset commands")
    p.add_argument("--gate-untrusted", action="store_true",
                   help="[DEPRECATED] if the project is not machine-local-trusted, "
                        "fall back to --safe-preset-only. Kept for back-compat; "
                        "new code should rely on the host agent / CI runner sandbox "
                        "instead. Will be removed in a future major version.")
    p.add_argument("--no-plan-gate", action="store_true",
                   help="skip plan-check from the default pipeline (opt out of the "
                        "v0.6+ deprecation gate; equivalent to v0.5.x behavior)")
    p.add_argument("--json", action="store_true", help="force JSON output (default)")
    p.add_argument("--jobs", type=int, default=1, metavar="N",
                   help="run up to N pipeline stages in parallel (default 1 = "
                        "sequential, byte-identical to pre-scheduler behavior). "
                        "Requires [stages.<name>].depends_on declarations for "
                        "non-default DAGs. Respects expected_mem_gb, "
                        "expected_cpu_cores, and license_token throttles per "
                        "stage; see docs/JSON-CONTRACT.md.")
    args = p.parse_args(argv)

    if args.jobs < 1:
        p.error("--jobs must be >= 1")

    config_path = Path(args.config)

    # --init runs in cwd, no flow.toml required (it's being created).
    if args.init:
        init_out = run_init(
            Path.cwd(),
            with_templates=args.with_templates,
            hdl=args.hdl,
            target=args.target,
            scope=args.scope,
            top=args.top,
            interactive=not args.non_interactive,
        )
        print(json.dumps(init_out, indent=2))
        return 0 if init_out.get("status") == "pass" else 1

    # --doctor is the one path that runs even without a flow.toml — it
    # is specifically designed to diagnose missing-config + other setup
    # gaps. Wire it before the config_path.exists() guard.
    if args.doctor:
        doctor_out = run_doctor(config_path)
        print(json.dumps(doctor_out, indent=2))
        return 1 if doctor_out.get("status") in ("fail", "blocked") else 0

    if not config_path.exists():
        print(json.dumps({"error": f"config not found: {config_path}"}))
        return 2

    safe = args.safe_preset_only
    trust_note = None
    if args.gate_untrusted and not safe:
        if not _project_is_trusted(_project_root(config_path)):
            safe = True
            trust_note = (
                "project is not in the machine-local trust list, so this ran in "
                "safe-preset mode: project-defined stages were skipped and placeholder "
                "values were validated. To run project-defined tool commands, trust it "
                f"on this machine — add its absolute path to {_trust_file_path()} "
                "(or export LOGICPILOT_TRUST_PROJECT=1) — then re-run."
            )
    cfg = load_config(config_path, safe_preset_only=safe)

    # v0.7a §4a.4: schema validation. Non-fatal in v0.7a — surface typos
    # as warnings so users discover them in CI output without breaking
    # any project. A later milestone may upgrade specific checks to
    # hard errors via the standard deprecation cycle protocol.
    config_warnings = format_errors(validate(cfg))

    if args.list:
        # Resolve each stage so the user sees the detected HDL and which tool
        # would actually run (and what's missing) BEFORE running anything.
        import shutil as _shutil

        def _builtin_list_entry(name: str, tool: str, hdl) -> dict:
            """List-format entry for one built-in; downgrades to needs-install
            when a registered required binary is absent from PATH.

            Two readiness flavors mirror tools.py:
            - BUILTIN_STAGES_NEEDING_TOOL (all-of): every listed binary
              must be present.
            - BUILTIN_STAGES_NEEDING_ANY_TOOL (any-of): at least one
              listed binary must be present.
            """
            needed_all = BUILTIN_STAGES_NEEDING_TOOL.get(name)
            if needed_all:
                missing = [b for b in needed_all if _shutil.which(b) is None]
                if missing:
                    entry: dict = {
                        "status": "needs-install",
                        "hdl": hdl,
                        "tool": tool,
                        "probes": list(needed_all),
                        "missing": missing,
                    }
                    hints = hints_for(missing)
                    if hints:
                        entry["install_hint"] = hints
                    return entry

            needed_any = BUILTIN_STAGES_NEEDING_ANY_TOOL.get(name)
            if needed_any:
                present = [b for b in needed_any if _shutil.which(b) is not None]
                if not present:
                    entry = {
                        "status": "needs-install",
                        "hdl": hdl,
                        "tool": tool,
                        "probes": list(needed_any),
                        "missing": list(needed_any),
                        "missing_semantics": "any_of",
                    }
                    hints = hints_for(list(needed_any))
                    if hints:
                        entry["install_hint"] = hints
                    return entry
                return {
                    "status": "runnable",
                    "hdl": hdl,
                    "tool": tool,
                    "probes": list(needed_any),
                    "backend_chosen": present[0],
                    "timeout_s": None,
                }

            return {
                "status": "runnable",
                "hdl": hdl,
                "tool": tool,
                "probes": list(needed_all) if needed_all else [],
                "timeout_s": None,
            }

        stage_info = {
            "plan-check": _builtin_list_entry("plan-check", "built-in-plan-check", None),
            "audit": _builtin_list_entry("audit", "built-in-source-audit", resolve_hdl_scope(cfg, "src")),
            "tb-audit": _builtin_list_entry("tb-audit", "built-in-testbench-audit", resolve_hdl_scope(cfg, "tb")),
            "formal": _builtin_list_entry("formal", "built-in-formal", None),
            "report": _builtin_list_entry("report", "built-in-report", resolve_hdl(cfg)),
        }
        for s in cfg["_stages"]:
            r = resolve_stage(s, cfg)
            if "blocked" in r:
                stage_info[s] = {
                    "status": "needs-install",
                    "hdl": r.get("hdl"),
                    "detail": r["blocked"],
                    "candidates": r.get("candidates", []),
                }
            else:
                stage_info[s] = {
                    "status": "runnable",
                    "hdl": r.get("hdl"),
                    "tool": r.get("tool") or "(fixed cmd)",
                    "probes": r.get("probes", []),
                    "timeout_s": _coerce_timeout(r.get("timeout_s")),
                }
        list_out = {
            "preset": cfg.get("toolchain", {}).get("preset"),
            "safe_preset_only": cfg.get("_safe_preset_only", False),
            "hdl": resolve_hdl(cfg),
            "hdl_info": resolve_hdl_info(cfg),
            "stages": stage_info,
            "vars": build_vars(cfg),
        }
        if config_warnings:
            list_out["config_warnings"] = config_warnings
        print(json.dumps(list_out, indent=2))
        return 0

    if args.tools:
        tools_out = discover_tools(cfg)
        if config_warnings:
            tools_out["config_warnings"] = config_warnings
        print(json.dumps(tools_out, indent=2))
        return 0

    if not args.stage:
        p.error("stage is required (or use --list)")

    if args.stage == "all":
        out = run_all(
            cfg,
            print_cmd=args.print_cmd,
            no_plan_gate=args.no_plan_gate,
            strict_plan=_strict_plan_from_env(),
            experimental=active_experimental,
            jobs=args.jobs,
        )
    else:
        # Direct single-stage invocation keeps hard-fail behavior for plan-check
        # so users running `python3 logicpilot.py plan-check` get the same
        # answer as before the v0.6 deprecation cycle.
        out = run_stage(
            args.stage, cfg, print_cmd=args.print_cmd,
            experimental=active_experimental,
        )

    if trust_note:
        out["safe_mode_note"] = trust_note

    if config_warnings:
        out["config_warnings"] = config_warnings

    exp_warnings = experimental_warnings(active_experimental)
    if exp_warnings:
        out.setdefault("warnings", []).extend(exp_warnings)
        out["experimental_active"] = sorted(active_experimental)

    print(json.dumps(out, indent=2))
    bad = out.get("overall") in ("fail", "blocked", "timeout") or out.get("status") in ("fail", "blocked", "timeout")
    return 1 if bad else 0
