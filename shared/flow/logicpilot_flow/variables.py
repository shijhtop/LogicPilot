"""LogicPilot hardware flow internals."""
from __future__ import annotations


import re
import shlex
import sys
from pathlib import Path

from .config import _expand_globs, resolve_hdl_info

_UNSAFE_SHELL_CHARS = ";|&$`<>\"'\\\n\r"


def _resolve_project_path(root: Path, value) -> Path:
    p = Path(str(value))
    return (p if p.is_absolute() else root / p).resolve()


def _assert_under_project(key: str, path: Path, root: Path) -> None:
    """In safe-preset mode, path-like placeholders must stay inside the project."""
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        sys.exit(
            f"error: safe-preset mode rejects '{key}' outside project root: {resolved}. "
            "Move the file under the project, or — only if this project is trusted — "
            "re-run without --safe-preset-only."
        )


def _safe_project_path(root: Path, key: str, value) -> str:
    if not value:
        return ""
    path = _resolve_project_path(root, value)
    _assert_under_project(key, path, root)
    return str(path)


def _looks_path_like(key: str, value: str) -> bool:
    return key.endswith(("_file", "_dir", "_path")) or "/" in value or "\\" in value

def _tcl_word(value: str) -> str:
    """Quote one file/path as a Tcl list element.

    This is intentionally conservative. It keeps normal paths readable and makes
    paths containing spaces safe inside Vivado/Quartus Tcl `[list ...]`. Both
    braces are escaped so a value can neither unbalance the wrapping `{...}` nor
    inject a Tcl command/variable substitution from inside it.
    """
    s = str(value).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return "{" + s + "}"

def _tcl_list(values: list[str]) -> str:
    return " ".join(_tcl_word(v) for v in values)

def _assert_safe_value(key: str, value: str) -> None:
    """Reject shell-breakout metacharacters in an untrusted placeholder value."""
    bad = sorted({c for c in str(value) if c in _UNSAFE_SHELL_CHARS})
    if bad:
        printable = ", ".join(repr(c) for c in bad)
        sys.exit(
            f"error: flow.toml value for '{key}' contains shell metacharacter(s) "
            f"{printable}, which are not allowed in safe-preset mode. Module, "
            f"device, and path names interpolated into commands must not contain "
            f"shell metacharacters. Fix the value, or — only if this project is "
            f"trusted — re-run without --safe-preset-only."
        )

def build_vars(cfg: dict) -> dict:
    root: Path = cfg["_root"]
    proj = cfg.get("project", {})
    tc = cfg.get("toolchain", {})
    activity_cfg = cfg.get("activity", {})
    power_cfg = cfg.get("power", {})
    build = root / proj.get("build_dir", "build")
    if cfg.get("_safe_preset_only"):
        _assert_under_project("project.build_dir", build, root)
    safe = bool(cfg.get("_safe_preset_only"))
    src = _expand_globs(proj.get("src_ordered", proj.get("src", [])), root, confine_to_root=safe)
    tb = _expand_globs(proj.get("tb_ordered", proj.get("tb", [])), root, confine_to_root=safe)
    constraints_path = str(root / proj.get("constraints", "")) if proj.get("constraints") else ""
    if cfg.get("_safe_preset_only") and constraints_path:
        _assert_under_project("project.constraints", Path(constraints_path), root)

    # In safe-preset mode, validate raw source/testbench paths too. shlex.quote
    # makes them safe as standalone shell words, but several shipped presets
    # interpolate {src} INSIDE their own single quotes (e.g. yosys -p '... {src}
    # ...'), where a quoted value can still close the surrounding quote. A real
    # source file never contains a shell metacharacter, so rejecting it here is
    # safe and closes that injection path.
    if cfg.get("_safe_preset_only"):
        for s in src:
            _assert_safe_value("project.src path", s)
            _assert_under_project("project.src path", Path(s), root)
        for t in tb:
            _assert_safe_value("project.tb path", t)
            _assert_under_project("project.tb path", Path(t), root)

    def _maybe_project_path(value, key: str = "path") -> str:
        if not value:
            return ""
        path = _resolve_project_path(root, value)
        if cfg.get("_safe_preset_only"):
            _assert_under_project(key, path, root)
        return str(path)

    saif_file = _maybe_project_path(activity_cfg.get("saif_file", ""), "activity.saif_file")
    vcd_file = _maybe_project_path(activity_cfg.get("vcd_file", ""), "activity.vcd_file")
    activity_file = _maybe_project_path(activity_cfg.get("activity_file", ""), "activity.activity_file") or saif_file or vcd_file
    activity_instance = str(activity_cfg.get("instance", activity_cfg.get("activity_instance", "")))

    hdl_info = resolve_hdl_info(cfg)
    base = {
        "top": proj.get("top", "top"),
        "tb_top": proj.get("tb_top", f"{proj.get('top', 'top')}_tb"),
        # Shell context (most open-source presets)
        "src": " ".join(shlex.quote(s) for s in src),
        "tb": " ".join(shlex.quote(s) for s in tb),
        "build": str(build),
        "root": str(root),
        "constraints": constraints_path,
        "saif_file": saif_file,
        "vcd_file": vcd_file,
        "activity_file": activity_file,
        "activity_instance": activity_instance,
        # Tcl list context (Vivado/Quartus presets)
        "src_tcl": _tcl_list(src),
        "tb_tcl": _tcl_list(tb),
        "build_tcl": _tcl_word(str(build)),
        "root_tcl": _tcl_word(str(root)),
        "constraints_tcl": _tcl_word(constraints_path) if constraints_path else "",
        "saif_file_tcl": _tcl_word(saif_file),
        "vcd_file_tcl": _tcl_word(vcd_file),
        "activity_file_tcl": _tcl_word(activity_file),
        "activity_instance_tcl": _tcl_word(activity_instance),
        "family": tc.get("family", ""),
        "device": tc.get("device", ""),
        "package": tc.get("package", ""),
        "clock_mhz": str(proj.get("clock_mhz", "")),
        "hdl": hdl_info["project"],
        "rtl_hdl": hdl_info["rtl"],
        "tb_hdl": hdl_info["tb"],
    }
    # Auto-expose any other scalar [project]/[toolchain]/[activity]/[power] keys
    # as placeholders so flows can add their own without editing this file. ASIC
    # presets use this for liberty/lef/sdc/pdk/platform; power presets use it for
    # voltage/temperature/budget/activity knobs. Path-like keys (name ends in
    # _file/_dir/_path or value looks like a path) are resolved relative to the
    # project root. Existing base keys are not overwritten.
    for section in (proj, tc, activity_cfg, power_cfg):
        for k, v in section.items():
            if k in base or not isinstance(v, (str, int, float, bool)):
                continue
            sval = str(v)
            if isinstance(v, str) and _looks_path_like(k, sval):
                path = _resolve_project_path(root, sval)
                if cfg.get("_safe_preset_only"):
                    _assert_under_project(k, path, root)
                sval = str(path)
            base[k] = sval

    # Safe-preset mode: the project flow.toml is untrusted. Reject any bare
    # shell-context placeholder value carrying a metacharacter before it can be
    # interpolated into a shipped preset's shell=True command. Tcl-quoted
    # variants (…_tcl) are wrapped in `{...}` and the joined src/tb strings are
    # already validated component-by-component above, so skip those here.
    if cfg.get("_safe_preset_only"):
        for k, v in base.items():
            if k.endswith("_tcl") or k in ("src", "tb"):
                continue
            _assert_safe_value(k, str(v))
    return base

def render(template: str, variables: dict) -> str:
    def _sub(m):
        name = m.group(1)
        return str(variables[name]) if name in variables else m.group(0)
    return _PLACEHOLDER_RE.sub(_sub, template)

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
