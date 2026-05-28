"""LogicPilot hardware flow internals."""
from __future__ import annotations


import shutil

from .config import resolve_hdl, resolve_hdl_info
from .install_hints import hints_for
from .stages import (
    BUILTIN_STAGES,
    BUILTIN_STAGES_NEEDING_ANY_TOOL,
    BUILTIN_STAGES_NEEDING_TOOL,
    resolve_stage,
)
from .utils import _coerce_timeout

KNOWN_TOOL_PROBES = {
    "audit": ["built-in-source-audit"],
    "testbench_audit": ["built-in-testbench-audit"],
    "report": ["built-in-report"],
    "lint": ["verilator", "verible-verilog-lint", "ghdl", "nvc"],
    "simulation": ["iverilog", "vvp", "verilator", "xvlog", "xelab", "xsim", "vsim", "vcs", "xrun", "ghdl", "nvc", "cocotb-config"],
    "synthesis": ["yosys", "vivado", "quartus_sh", "dc_shell", "dc_shell-t", "genus"],
    "power_analysis": ["vivado", "quartus_sh", "pt_shell", "openroad", "genus"],
    "formal_equivalence": ["sby", "yosys", "formality", "lec"],
    "fpga_backend": ["nextpnr-ice40", "nextpnr-ecp5", "openFPGALoader", "icepack", "vivado", "quartus_sh"],
    "asic_backend": ["openroad", "flow.tcl", "make", "klayout", "magic", "netgen", "innovus", "icc2_shell", "pt_shell"],
}


def _builtin_stage_entry(name: str) -> dict:
    """Build the /lp-tools row for one built-in stage.

    Two readiness flavors:
    - BUILTIN_STAGES_NEEDING_TOOL (all-of): every listed binary must be
      on PATH (e.g. saif-gen needs vcd2saif).
    - BUILTIN_STAGES_NEEDING_ANY_TOOL (any-of): at least ONE listed
      binary must be on PATH (e.g. formal accepts sby OR jaspergold OR
      vcf OR qverify).
    """
    needed_all = BUILTIN_STAGES_NEEDING_TOOL.get(name)
    if needed_all:
        missing = [b for b in needed_all if shutil.which(b) is None]
        if missing:
            entry: dict = {
                "status": "blocked",
                "tool": f"built-in-{name}",
                "probes": list(needed_all),
                "missing": missing,
                "builtin": True,
            }
            hints = hints_for(missing)
            if hints:
                entry["install_hint"] = hints
            return entry

    needed_any = BUILTIN_STAGES_NEEDING_ANY_TOOL.get(name)
    if needed_any:
        present = [b for b in needed_any if shutil.which(b) is not None]
        if not present:
            entry = {
                "status": "blocked",
                "tool": f"built-in-{name}",
                "probes": list(needed_any),
                "missing": list(needed_any),
                "missing_semantics": "any_of",
                "builtin": True,
            }
            hints = hints_for(list(needed_any))
            if hints:
                entry["install_hint"] = hints
            return entry
        # Show which backend will win.
        return {
            "status": "runnable",
            "tool": f"built-in-{name}",
            "probes": list(needed_any),
            "backend_chosen": present[0],
            "timeout_s": None,
            "builtin": True,
        }

    probes_all = list(needed_all) if needed_all else []
    return {
        "status": "runnable",
        "tool": f"built-in-{name}",
        "probes": probes_all,
        "timeout_s": None,
        "builtin": True,
    }

def discover_tools(cfg: dict | None = None) -> dict:
    groups = {}
    for group, probes in KNOWN_TOOL_PROBES.items():
        groups[group] = {
            probe: True if probe.startswith("built-in-") else bool(shutil.which(probe))
            for probe in probes
        }
    out = {"tool_groups": groups}
    if cfg is not None:
        stages = {}
        # v0.6 F5c follow-up: built-in stages (plan-check, audit, tb-audit,
        # report) are always runnable since they need no external tool. They
        # used to be invisible to /lp-tools because we only iterated the
        # project's declared stages. Now they appear with builtin=True so
        # the agent can list them without consulting a separate doc.
        for name in BUILTIN_STAGES:
            stages[name] = _builtin_stage_entry(name)
        for name in cfg.get("_stages", {}):
            r = resolve_stage(name, cfg)
            if "blocked" in r:
                blocked_entry: dict = {
                    "status": "blocked",
                    "hdl": r.get("hdl"),
                    "detail": r["blocked"],
                    "candidates": r.get("candidates", []),
                    "missing": r.get("missing", []),
                    "missing_paths": r.get("missing_paths", []),
                }
                # v0.7a §4a.3: install_hint for missing tools we know how to install.
                hints = hints_for(r.get("missing", []))
                if hints:
                    blocked_entry["install_hint"] = hints
                stages[name] = blocked_entry
            else:
                stages[name] = {
                    "status": "runnable",
                    "hdl": r.get("hdl"),
                    "tool": r.get("tool") or "fixed-command",
                    "probes": r.get("probes", []),
                    "timeout_s": _coerce_timeout(r.get("timeout_s")),
                }
        out.update({
            "preset": cfg.get("toolchain", {}).get("preset"),
            "safe_preset_only": cfg.get("_safe_preset_only", False),
            "hdl": resolve_hdl(cfg),
            "hdl_info": resolve_hdl_info(cfg),
            "stages": stages,
        })
    return out
