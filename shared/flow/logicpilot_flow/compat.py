"""Aggregated public API surface for the LogicPilot flow driver."""
from __future__ import annotations

import shutil

from .audit import run_source_audit, run_testbench_audit
from .cli import main
from .plan_check import run_plan_check
from .config import (
    HDL_EXT,
    _as_list,
    _detect_hdl_from_files,
    _expand_globs,
    _normalize_hdl,
    _project_root,
    load_config,
    resolve_hdl,
    resolve_hdl_info,
    resolve_hdl_scope,
)
from .diagnostics import (
    QUALITY_RED_FLAGS,
    power_assumptions,
    power_warnings,
    quality_warnings,
    verification_warnings,
)
from .metrics import DEFAULT_METRIC_PATTERNS, evaluate_checks, parse_metrics
from .report import run_report
from .runner import run_all, run_stage
from .stages import (
    BUILTIN_STAGES,
    STAGE_ORDER,
    _candidate_supports,
    _checks_for,
    _missing_path_probes,
    _missing_probes,
    _path_probes_for,
    _probes_for,
    _stage_hdl_scope,
    resolve_stage,
)
from .tools import KNOWN_TOOL_PROBES, discover_tools
from .trust import _project_is_trusted, _trust_file_path
from .utils import _coerce_timeout, _timeout_output
from .variables import (
    _PLACEHOLDER_RE,
    _UNSAFE_SHELL_CHARS,
    _assert_safe_value,
    _assert_under_project,
    _safe_project_path,
    _tcl_list,
    _tcl_word,
    build_vars,
    render,
)

__all__ = ['shutil', 'main', 'HDL_EXT', '_as_list', '_detect_hdl_from_files', '_expand_globs', '_normalize_hdl', '_project_root', 'load_config', 'resolve_hdl', 'resolve_hdl_info', 'resolve_hdl_scope', 'QUALITY_RED_FLAGS', 'power_assumptions', 'power_warnings', 'quality_warnings', 'verification_warnings', 'DEFAULT_METRIC_PATTERNS', 'evaluate_checks', 'parse_metrics', 'run_report', 'run_all', 'run_stage', 'BUILTIN_STAGES', 'STAGE_ORDER', '_candidate_supports', '_checks_for', '_missing_path_probes', '_missing_probes', '_path_probes_for', '_probes_for', '_stage_hdl_scope', 'resolve_stage', 'KNOWN_TOOL_PROBES', 'discover_tools', '_project_is_trusted', '_trust_file_path', '_coerce_timeout', '_timeout_output', '_PLACEHOLDER_RE', '_UNSAFE_SHELL_CHARS', '_assert_safe_value', '_assert_under_project', '_safe_project_path', '_tcl_list', '_tcl_word', 'build_vars', 'render', 'run_source_audit', 'run_testbench_audit', 'run_plan_check']
