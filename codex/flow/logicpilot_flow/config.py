"""LogicPilot hardware flow internals."""
from __future__ import annotations


import glob
import os
import sys
from pathlib import Path

HDL_EXT = {
    ".v": "verilog", ".vh": "verilog",
    ".sv": "verilog", ".svh": "verilog",
    ".vhd": "vhdl", ".vhdl": "vhdl",
}

# ---- TOML loading (3.11+ stdlib, else tomli fallback) ----------------------
try:
    import tomllib  # type: ignore
    def _load_toml(p: Path) -> dict:
        with open(p, "rb") as f:
            return tomllib.load(f)
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli  # type: ignore
        def _load_toml(p: Path) -> dict:
            with open(p, "rb") as f:
                return tomli.load(f)
    except ModuleNotFoundError:
        sys.exit("error: need Python 3.11+ or `pip install tomli`")

def _project_root(config_path: Path) -> Path:
    return config_path.resolve().parent

def _as_list(value) -> list:
    """Normalize a TOML scalar/list into a Python list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def _glob_match_limit() -> int:
    raw = os.environ.get("LOGICPILOT_MAX_GLOB_MATCHES", "10000")
    try:
        return max(1, int(raw))
    except ValueError:
        return 10000


def _safe_pattern_path(root: Path, pattern: str) -> Path:
    """Return the absolute pattern path, rejecting root escapes in safe mode.

    Globs may contain files that do not exist yet, so we cannot resolve the full
    path strictly. Rejecting absolute paths outside the workspace and any `..`
    segment keeps automatic hooks from enumerating arbitrary parent directories.
    Trusted/manual runs can still use external source trees without safe mode.
    """
    raw = Path(pattern)
    if ".." in raw.parts:
        sys.exit(
            f"error: safe-preset mode rejects glob outside project root: {pattern!r}. "
            "Keep source/testbench patterns under the project, or trust the project "
            "locally and re-run without --safe-preset-only."
        )
    candidate = raw if raw.is_absolute() else root / raw
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        sys.exit(
            f"error: safe-preset mode rejects glob outside project root: {pattern!r}. "
            "Keep source/testbench patterns under the project, or trust the project "
            "locally and re-run without --safe-preset-only."
        )
    return candidate


def _expand_globs(patterns, root: Path, *, confine_to_root: bool = False) -> list[str]:
    out: list[str] = []
    limit = _glob_match_limit() if confine_to_root else 0
    for pat in _as_list(patterns):
        pat_text = str(pat)
        base = _safe_pattern_path(root, pat_text) if confine_to_root else root / pat_text
        matched: list[str] = []
        for item in glob.iglob(str(base), recursive=True):
            matched.append(item)
            if limit and len(matched) >= limit:
                break
        if matched:
            out.extend(sorted(matched))
        else:
            # keep literal (e.g. an explicit file that doesn't exist yet)
            out.append(str(base))
    return out

def _detect_hdl_from_files(files: list[str], default: str = "verilog") -> str:
    families = set()
    for f in files:
        fam = HDL_EXT.get(Path(f).suffix.lower())
        if fam:
            families.add(fam)
    if families == {"verilog"}:
        return "verilog"
    if families == {"vhdl"}:
        return "vhdl"
    if len(families) > 1:
        return "mixed"
    return default

def _normalize_hdl(value: object) -> str:
    declared = str(value or "auto").lower()
    if declared in ("verilog", "systemverilog", "sv"):
        return "verilog"
    if declared in ("vhdl", "vhd"):
        return "vhdl"
    if declared == "mixed":
        return "mixed"
    return "auto"

def resolve_hdl_scope(cfg: dict, scope: str = "project") -> str:
    """Resolve HDL language for a specific stage scope.

    `resolve_hdl()` is kept as the project-wide/legacy answer (src+tb). Stages
    may be more precise: synthesis/lint should usually inspect RTL sources only,
    while behavioral sim must consider both RTL and testbench languages.
    """
    root: Path = cfg["_root"]
    proj = cfg.get("project", {})
    scope = (scope or "project").lower()
    safe = bool(cfg.get("_safe_preset_only"))
    src_files = _expand_globs(proj.get("src_ordered", proj.get("src", [])), root, confine_to_root=safe)
    tb_files = _expand_globs(proj.get("tb_ordered", proj.get("tb", [])), root, confine_to_root=safe)

    rtl_declared = _normalize_hdl(proj.get("rtl_hdl", proj.get("hdl", "auto")))
    tb_declared = _normalize_hdl(proj.get("tb_hdl", "auto"))

    if scope in ("src", "rtl", "rtl-only"):
        return rtl_declared if rtl_declared != "auto" else _detect_hdl_from_files(src_files)
    if scope in ("tb", "testbench", "testbench-only"):
        if tb_declared != "auto":
            return tb_declared
        detected = _detect_hdl_from_files(tb_files, default="")
        return detected or resolve_hdl_scope(cfg, "src")

    # project / src+tb / all: preserve the legacy explicit override behavior,
    # but auto-detection includes the testbench and therefore exposes mixed RTL/TB.
    if scope in ("project", "src+tb", "all", "design"):
        project_declared = _normalize_hdl(proj.get("hdl", "auto"))
        # If there is no testbench, preserve the legacy explicit override.
        # If a TB exists, combine explicit RTL language with auto/explicit TB
        # language so VHDL RTL + Verilog TB is reported as mixed for sim/GLS.
        if project_declared != "auto" and not tb_files:
            return project_declared
        families = {
            fam for fam in (
                resolve_hdl_scope(cfg, "src"),
                resolve_hdl_scope(cfg, "tb") if tb_files else "",
            ) if fam
        }
        if families == {"verilog"}:
            return "verilog"
        if families == {"vhdl"}:
            return "vhdl"
        if "mixed" in families or len(families) > 1:
            return "mixed"
        return "verilog"

    # Unknown scope: be conservative and use project-wide detection.
    return resolve_hdl_scope(cfg, "project")

def resolve_hdl_info(cfg: dict) -> dict:
    return {
        "project": resolve_hdl_scope(cfg, "project"),
        "rtl": resolve_hdl_scope(cfg, "src"),
        "tb": resolve_hdl_scope(cfg, "tb"),
    }

def load_config(config_path: Path, *, safe_preset_only: bool = False) -> dict:
    cfg = _load_toml(config_path)
    root = _project_root(config_path)

    preset_name = cfg.get("toolchain", {}).get("preset")
    merged_stages: dict = {}
    pipeline_order: list = []
    stage_sources: dict = {}
    if preset_name:
        shipped_preset_dir = Path(__file__).resolve().parent.parent / "presets"
        if safe_preset_only:
            # Hook/safe mode: never run project-local stage commands or local
            # preset files. Only shipped presets are eligible; project values
            # may still feed placeholders (top/src/device/etc.).
            preset_path = shipped_preset_dir / f"{preset_name}.toml"
            preset_source = "shipped_preset"
        else:
            preset_path = root / "presets" / f"{preset_name}.toml"
            if not preset_path.exists():
                # also look next to this script (the shipped presets)
                preset_path = shipped_preset_dir / f"{preset_name}.toml"
            preset_source = "project_config" if preset_path.parent == root / "presets" else "shipped_preset"
        if not preset_path.exists():
            sys.exit(f"error: preset '{preset_name}' not found ({preset_path})")
        preset = _load_toml(preset_path)
        merged_stages.update(preset.get("stages", {}))
        stage_sources.update({name: preset_source for name in preset.get("stages", {})})
        pipeline_order = preset.get("pipeline", {}).get("order", [])

    # Project stages override preset stages wholesale (per stage). In safe mode
    # they are ignored, because project-local shell is not trustworthy for
    # automatic hooks.
    if not safe_preset_only:
        for name, spec in cfg.get("stages", {}).items():
            merged_stages[name] = spec
            stage_sources[name] = "project_config"

    # Pipeline ORDER is a list of stage NAMES — no shell content, no
    # injection surface. Honor the project's override even in safe
    # mode. Without this, declaring `[pipeline].order = [...]` is
    # silently ignored whenever `--gate-untrusted` triggers (which is
    # the common case for fresh checkouts and CI integration). Stages
    # in the order that don't have a runnable spec just resolve to
    # `skipped` — same as today.
    pipeline_order = cfg.get("pipeline", {}).get("order", pipeline_order)

    cfg["_stages"] = merged_stages
    cfg["_stage_sources"] = stage_sources
    cfg["_pipeline"] = pipeline_order
    cfg["_root"] = root
    cfg["_safe_preset_only"] = safe_preset_only
    return cfg

def resolve_hdl(cfg: dict) -> str:
    """Backward-compatible project-wide HDL answer (RTL + testbench)."""
    return resolve_hdl_scope(cfg, "project")
