"""LogicPilot hardware flow internals."""
from __future__ import annotations


import shutil
from pathlib import Path

from .config import _as_list, resolve_hdl_scope
from .variables import build_vars, render

BUILTIN_STAGES = (
    "plan-check", "audit", "tb-audit", "cdc-check", "constraints",
    "formal", "report",
)

# Built-ins that need an external tool on PATH to actually run. They show
# up in BUILTIN_STAGES so /lp-tools and --list mention them, but tools.py
# and cli.py must probe the binary before claiming "runnable". Tuple
# semantics: ALL listed binaries must be present.
BUILTIN_STAGES_NEEDING_TOOL: dict[str, tuple[str, ...]] = {}

# Sibling structure for "ANY-of" semantics — at least ONE of the listed
# binaries must be on PATH. Used by the formal stage which dispatches
# to whichever backend is installed (sby / jaspergold / vcf / qverify).
BUILTIN_STAGES_NEEDING_ANY_TOOL: dict[str, tuple[str, ...]] = {
    "formal": ("sby", "jaspergold", "vcf", "qverify"),
    "cdc-check": ("sg_shell", "verilator"),
}

# plan-check sits at the head of the default `all` pipeline as of v0.6.
# v0.6 runs it in soft mode (warn instead of fail) so the change is
# non-breaking; v0.7b flips it to hard-fail. Two escape hatches preserve
# the old behavior throughout the deprecation cycle:
#   --no-plan-gate   removes it from the pipeline (= v0.5.x behavior)
#   LOGICPILOT_STRICT=1   forces hard-fail today (= v0.7b preview)
# See runner.run_all + cli._strict_plan_from_env for the plumbing.
STAGE_ORDER = ["plan-check", "audit", "tb-audit", "lint", "sim", "synth", "pnr", "power", "gls", "lec", "report"]

def _stage_hdl_scope(name: str, spec: dict) -> str:
    if isinstance(spec, dict) and spec.get("hdl_scope"):
        return str(spec["hdl_scope"])
    # Default to RTL-only for stages that should not be poisoned by a
    # differently-written testbench. Behavioral/GLS sim must inspect both.
    if name in ("lint", "synth"):
        return "src"
    if name in ("sim", "gls"):
        return "src+tb"
    return "src"

def _candidate_supports(cand: dict, family: str) -> bool:
    """A candidate's `hdl` list must cover the stage HDL family.

    A 'mixed' stage needs a tool that handles both Verilog/SystemVerilog and
    VHDL. Language-agnostic fixed stages should omit `hdl`.
    """
    supported = {str(h).lower() for h in cand.get("hdl", ["verilog"])}
    if family == "mixed":
        return {"verilog", "vhdl"} <= supported
    return family in supported

def _probes_for(spec: dict) -> list[str]:
    probes: list[str] = []
    if "probe" in spec and spec.get("probe"):
        probes.append(str(spec["probe"]))
    for probe in _as_list(spec.get("probes")):
        if probe:
            probes.append(str(probe))
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(probes))

def _missing_probes(probes: list[str]) -> list[str]:
    return [probe for probe in probes if not shutil.which(probe)]

def _path_probes_for(spec: dict) -> list[str]:
    return [str(p) for p in _as_list(spec.get("path_probes")) if p]

def _missing_path_probes(spec: dict, cfg: dict) -> list[str]:
    paths = _path_probes_for(spec)
    if not paths:
        return []
    variables = build_vars(cfg)
    root: Path = cfg["_root"]
    missing: list[str] = []
    for template in paths:
        rendered = render(template, variables)
        p = Path(rendered)
        if not p.is_absolute():
            p = root / p
        if not p.exists():
            missing.append(rendered)
    return missing

def _checks_for(stage_spec: dict, chosen: dict | None = None) -> dict:
    checks = dict(stage_spec.get("checks", {}) if isinstance(stage_spec, dict) else {})
    if chosen:
        checks.update(chosen.get("checks", {}))
    return checks

def resolve_stage(name: str, cfg: dict) -> dict:
    """Resolve a stage spec into a concrete command + chosen tool.

    Returns a dict with either {'cmd', 'tool', 'hdl'} on success, or
    {'blocked': reason, 'hdl': family, 'candidates': [...]} when no candidate
    matches the stage HDL / required probes are absent.
    """
    spec = cfg["_stages"][name]
    command_source = cfg.get("_stage_sources", {}).get(name, "project_config")

    # Flat string form: language-agnostic and cannot be probed. This is allowed
    # for project-local custom flows but shipped presets should prefer {cmd,
    # probes=[...]} so --tools can report readiness honestly.
    if isinstance(spec, str):
        family = resolve_hdl_scope(cfg, _stage_hdl_scope(name, {}))
        return {"cmd": spec, "tool": None, "hdl": family, "probes": [], "command_source": command_source}

    family = resolve_hdl_scope(cfg, _stage_hdl_scope(name, spec))

    # Fixed {cmd = "..."} form. It may declare hdl/probe(s)/timeout/checks.
    if "candidates" not in spec:
        if spec.get("hdl") and not _candidate_supports(spec, family):
            return {
                "blocked": f"stage '{name}' fixed command does not support HDL '{family}'",
                "hdl": family,
                "command_source": command_source,
                "candidates": [spec.get("name", "fixed-command")],
            }
        probes = _probes_for(spec)
        missing = _missing_probes(probes)
        missing_paths = _missing_path_probes(spec, cfg)
        if missing or missing_paths:
            reason_bits = []
            if missing:
                reason_bits.append(f"missing required tool(s): {', '.join(missing)}")
            if missing_paths:
                reason_bits.append(f"missing required path(s): {', '.join(missing_paths)}")
            return {
                "blocked": f"stage '{name}': " + "; ".join(reason_bits),
                "hdl": family,
                "command_source": command_source,
                "candidates": [spec.get("name", "fixed-command")],
                "missing": missing,
                "missing_paths": missing_paths,
            }
        return {
            "cmd": spec.get("cmd", ""),
            "tool": spec.get("name") or ("/".join(probes) if probes else None),
            "hdl": family,
            "command_source": command_source,
            "probes": probes,
            "path_probes": _path_probes_for(spec),
            "timeout_s": spec.get("timeout_s"),
            "checks": _checks_for(spec),
        }

    # Candidate list: filter by HDL support, then require every candidate probe
    # to be on PATH, in listed order (= priority). First usable candidate wins.
    cands = spec["candidates"]
    lang_ok = [c for c in cands if _candidate_supports(c, family)]
    if not lang_ok:
        return {
            "blocked": f"no candidate tool for stage '{name}' supports HDL '{family}'",
            "hdl": family,
            "command_source": command_source,
            "candidates": [c["name"] for c in cands if c.get("name")],
        }

    missing_by_candidate = []
    for c in lang_ok:
        probes = _probes_for(c)
        if not probes and c.get("name"):
            probes = [str(c["name"])]
        missing = _missing_probes(probes)
        missing_paths = _missing_path_probes(c, cfg) + _missing_path_probes(spec, cfg)
        if not missing and not missing_paths:
            primary = probes[0] if probes else c.get("name")
            return {
                "cmd": c["cmd"],
                "tool": c.get("name", primary),
                "hdl": family,
                "command_source": command_source,
                "probes": probes,
                "path_probes": _path_probes_for(spec) + _path_probes_for(c),
                "timeout_s": c.get("timeout_s", spec.get("timeout_s")),
                "checks": _checks_for(spec, c),
            }
        bits = []
        if missing:
            bits.append("tools " + ", ".join(missing))
        if missing_paths:
            bits.append("paths " + ", ".join(missing_paths))
        missing_by_candidate.append(f"{c.get('name', '?')} missing {'; '.join(bits)}")

    return {
        "blocked": f"stage '{name}': no installed tool for HDL '{family}'. "
                   f"Install one complete candidate: {'; '.join(missing_by_candidate)}",
        "hdl": family,
        "command_source": command_source,
        "candidates": [c.get("name") for c in lang_ok],
    }
