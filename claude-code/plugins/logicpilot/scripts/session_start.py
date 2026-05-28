#!/usr/bin/env python3
"""
SessionStart hook: if the current directory (or a parent) is a hardware-flow
project, inject a compact safe-mode tool-readiness summary. Non-blocking.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def find_flow_root(start: Path) -> Path | None:
    current = start.resolve(strict=False)
    while True:
        if (current / "flow.toml").is_file():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def emit_context(text: str) -> None:
    print(
        json.dumps(
            {
                "suppressOutput": True,
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": text,
                },
            },
            ensure_ascii=False,
        )
    )


def main() -> int:
    flow_root = find_flow_root(Path.cwd())
    if flow_root is None:
        return 0

    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        return 0
    driver = Path(plugin_root) / "flow" / "logicpilot.py"
    if not driver.is_file():
        return 0

    try:
        completed = subprocess.run(
            [sys.executable, str(driver), "--tools", "--config", "flow.toml", "--gate-untrusted"],
            cwd=str(flow_root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except Exception:
        return 0

    try:
        data = json.loads(completed.stdout.strip() or "{}")
    except Exception:
        return 0

    stages = data.get("stages") or {}
    if not stages:
        return 0

    hdl_info = data.get("hdl_info") or {"project": data.get("hdl", "?")}
    runnable = [name for name, value in stages.items() if value.get("status") == "runnable"]
    blocked = [name for name, value in stages.items() if value.get("status") == "blocked"]

    lines = ["[logicpilot] project detected (flow.toml)."]
    lines.append(
        "  HDL: project={project}, rtl={rtl}, tb={tb}".format(
            project=hdl_info.get("project", "?"),
            rtl=hdl_info.get("rtl", "?"),
            tb=hdl_info.get("tb", "?"),
        )
    )
    if runnable:
        lines.append("  runnable stages: " + ", ".join(runnable))
    if blocked:
        lines.append("  blocked stages: " + ", ".join(blocked))
        for stage in blocked[:4]:
            detail = stages[stage].get("detail", "")
            if detail:
                lines.append(f"    - {stage}: {detail}")
    lines.append("  Run /lp-tools for details; do not assume success from exit code alone.")

    emit_context("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
