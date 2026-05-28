"""Health check command: 'can I run LogicPilot here?' (v0.7a §4a.2).

`/lp-doctor` and `python3 logicpilot.py --doctor` walk a checklist that
answers a different question than `/lp-tools`:

- `/lp-tools` answers "what's installed on this machine".
- `/lp-doctor` answers "given this project + machine + config, can the
  user actually run the flow today, and if not, what's the cheapest fix".

Checks (in order):
1. Python version (>= 3.11 native, or >= 3.10 with the tomli backport).
2. flow.toml present + parses + schema-clean (no unknown sections or
   misspelled preset names — uses config_schema.validate()).
3. Project trust status (whether project-local stage commands will run).
4. External tool readiness (delegates to tools.discover_tools and
   surfaces install_hint for any blocked stage).
5. Smoke test: built-in report stage runs without errors (proves the
   driver + project root + log dir wiring works end-to-end).

Each check is one row in the output. Overall status is the worst of all
rows; the front-end agent can show only fail/warn rows and skip pass
rows to keep its context window lean.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .config_schema import format_errors, validate
from .install_hints import hints_for
from .tools import discover_tools


# --- per-check helpers -------------------------------------------------------

def _check_python() -> dict:
    """Python 3.11+ native, 3.10 needs tomli."""
    major, minor = sys.version_info[:2]
    version_str = f"{major}.{minor}.{sys.version_info[2]}"
    if (major, minor) >= (3, 11):
        return {
            "name": "python_version",
            "status": "pass",
            "detail": f"Python {version_str} (native tomllib)",
        }
    if (major, minor) == (3, 10):
        try:
            import tomli  # noqa: F401
            return {
                "name": "python_version",
                "status": "pass",
                "detail": f"Python {version_str} + tomli backport",
            }
        except ImportError:
            return {
                "name": "python_version",
                "status": "fail",
                "detail": (
                    f"Python {version_str} needs tomli backport "
                    "(pip install tomli)"
                ),
            }
    return {
        "name": "python_version",
        "status": "fail",
        "detail": (
            f"Python {version_str} unsupported — LogicPilot requires "
            "3.11+ native or 3.10 + tomli"
        ),
    }


def _check_flow_toml(config_path: Path) -> tuple[dict, dict | None]:
    """Returns (check_row, parsed_cfg_or_None). Loading + schema-validation
    happens here so downstream checks can reuse the parsed cfg."""
    if not config_path.exists():
        return (
            {
                "name": "flow_toml",
                "status": "fail",
                "detail": f"missing: {config_path}",
                "hint": "run /lp-init to scaffold one, or `cp shared/flow/flow.toml.example flow.toml`",
            },
            None,
        )

    # load_config handles parse + preset resolution; importing here keeps
    # the doctor decoupled from full driver initialization.
    try:
        from .config import load_config
        cfg = load_config(config_path, safe_preset_only=False)
    except SystemExit as e:
        # load_config calls sys.exit on hard config errors (e.g. unknown
        # preset name). Convert that to a doctor row instead of crashing.
        return (
            {
                "name": "flow_toml",
                "status": "fail",
                "detail": f"load_config rejected the file: {e}",
            },
            None,
        )
    except Exception as e:
        return (
            {
                "name": "flow_toml",
                "status": "fail",
                "detail": f"parse error: {type(e).__name__}: {e}",
            },
            None,
        )

    schema_errors = validate(cfg)
    if schema_errors:
        return (
            {
                "name": "flow_toml",
                "status": "warn",
                "detail": f"{len(schema_errors)} schema warning(s)",
                "warnings": format_errors(schema_errors),
            },
            cfg,
        )

    return (
        {
            "name": "flow_toml",
            "status": "pass",
            "detail": f"loaded {config_path.name}, schema clean",
        },
        cfg,
    )


def _check_trust(cfg: dict) -> dict:
    """Workspace trust state — whether project-local stage commands run."""
    from .trust import _project_is_trusted, _trust_file_path

    root = cfg["_root"]
    if _project_is_trusted(root):
        return {
            "name": "workspace_trust",
            "status": "pass",
            "detail": f"project trusted in {_trust_file_path()}",
        }
    return {
        "name": "workspace_trust",
        "status": "warn",
        "detail": "project NOT in machine-local trust list",
        "hint": (
            f"add {root} to {_trust_file_path()} to allow project-defined "
            "shell commands; otherwise --gate-untrusted falls back to "
            "safe-preset mode"
        ),
    }


def _check_tools(cfg: dict) -> list[dict]:
    """Per-stage readiness — one row per declared project stage."""
    out: list[dict] = []
    tools_view = discover_tools(cfg)
    for name, info in tools_view.get("stages", {}).items():
        if info.get("builtin"):
            continue  # built-ins are always runnable; not informative here
        row: dict[str, Any] = {
            "name": f"stage:{name}",
            "status": "pass" if info.get("status") == "runnable" else "blocked",
            "detail": info.get("detail") or info.get("tool") or "(unknown)",
        }
        if info.get("install_hint"):
            row["install_hint"] = info["install_hint"]
        out.append(row)
    return out


def _check_report_smoke(cfg: dict) -> dict:
    """End-to-end smoke: the built-in report stage runs without external
    tools and produces JSON. If THIS fails, the driver wiring is broken."""
    try:
        from .report import run_report
        result = run_report(cfg, print_cmd=False)
    except Exception as e:
        return {
            "name": "smoke_test",
            "status": "fail",
            "detail": f"built-in report stage crashed: {type(e).__name__}: {e}",
        }
    if result.get("status") in ("pass", "blocked"):
        # blocked is OK here — it just means no logs to aggregate yet.
        return {
            "name": "smoke_test",
            "status": "pass",
            "detail": f"report stage returned status={result.get('status')}",
        }
    return {
        "name": "smoke_test",
        "status": "fail",
        "detail": f"report stage returned status={result.get('status')}",
    }


# --- top-level --------------------------------------------------------------

def _worst_status(statuses: list[str]) -> str:
    """Status precedence: fail > blocked > warn > pass."""
    if "fail" in statuses:
        return "fail"
    if "blocked" in statuses:
        return "blocked"
    if "warn" in statuses:
        return "warn"
    return "pass"


def run_doctor(config_path: Path) -> dict:
    """Run all checks. Returns a standard envelope:
    {
      "stage": "doctor",
      "status": "pass" | "warn" | "fail" | "blocked",
      "checks": [...],
      "summary": {"pass": N, "warn": N, "fail": N, "blocked": N},
    }
    """
    checks: list[dict] = []
    checks.append(_check_python())

    flow_row, cfg = _check_flow_toml(config_path)
    checks.append(flow_row)

    if cfg is not None:
        checks.append(_check_trust(cfg))
        checks.extend(_check_tools(cfg))
        checks.append(_check_report_smoke(cfg))

    statuses = [c["status"] for c in checks]
    summary = {s: statuses.count(s) for s in ("pass", "warn", "fail", "blocked")}
    overall = _worst_status(statuses)

    out = {
        "stage": "doctor",
        "status": overall,
        "checks": checks,
        "summary": summary,
    }

    # Aggregate install_hints across all blocked stages so the agent can
    # show one consolidated install line instead of N separate ones.
    aggregated_missing: set[str] = set()
    for c in checks:
        for tool in c.get("install_hint", {}):
            aggregated_missing.add(tool)
    if aggregated_missing:
        out["install_hint"] = hints_for(sorted(aggregated_missing))

    return out
