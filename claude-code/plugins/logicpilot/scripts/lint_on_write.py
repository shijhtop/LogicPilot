#!/usr/bin/env python3
"""
PostToolUse hook: lint RTL after Claude writes/edits HDL.

Safety model:
  - Only runs when a flow.toml is found at or above the edited file.
  - Calls the driver with --gate-untrusted, so untrusted projects use
    safe-preset mode and trusted projects may run local stages.
  - Non-blocking: this hook exits 0 even when lint fails.
  - Opt out by setting LOGICPILOT_AUTO_LINT=0 in the user environment.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


HDL_SUFFIXES = {".v", ".sv", ".svh", ".vhd", ".vhdl"}
TB_MARKERS = ("_tb.", "_test.", "_tests.")


def is_hdl(path: str) -> bool:
    return Path(path).suffix.lower() in HDL_SUFFIXES


def is_testbench(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    name = Path(normalized).name
    return "/tb/" in normalized or any(marker in name for marker in TB_MARKERS)


def extract_candidate_paths(payload: dict[str, Any]) -> list[str]:
    tool_input = payload.get("tool_input") or {}
    paths: list[str] = []

    if isinstance(tool_input, dict):
        for key in ("file_path", "path"):
            value = tool_input.get(key)
            if isinstance(value, str):
                paths.append(value)

        for key in ("files", "edits"):
            items = tool_input.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, str):
                    paths.append(item)
                elif isinstance(item, dict):
                    for item_key in ("file_path", "path"):
                        value = item.get(item_key)
                        if isinstance(value, str):
                            paths.append(value)

    # Be tolerant of simplified hook payloads.
    for key in ("file_path", "path"):
        value = payload.get(key)
        if isinstance(value, str):
            paths.append(value)

    return paths


def resolve_for_walk(path_text: str, cwd: Path) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = cwd / path
    # strict=False keeps newly-written files and Windows paths usable.
    return path.resolve(strict=False)


def find_flow_root(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    while True:
        if (current / "flow.toml").is_file():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def emit_context(hook_event: str, text: str) -> None:
    print(
        json.dumps(
            {
                "suppressOutput": True,
                "hookSpecificOutput": {
                    "hookEventName": hook_event,
                    "additionalContext": text,
                },
            },
            ensure_ascii=False,
        )
    )


def main() -> int:
    try:
        payload_text = sys.stdin.read()
        payload = json.loads(payload_text) if payload_text.strip() else {}
    except Exception:
        return 0

    cwd = Path.cwd()
    file_path = next((p for p in extract_candidate_paths(payload) if is_hdl(p)), "")
    if not file_path or is_testbench(file_path):
        return 0

    flow_root = find_flow_root(resolve_for_walk(file_path, cwd))
    if flow_root is None:
        return 0

    if os.environ.get("LOGICPILOT_AUTO_LINT", "1") == "0":
        return 0

    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        return 0
    driver = Path(plugin_root) / "flow" / "logicpilot.py"
    if not driver.is_file():
        return 0

    cmd = [sys.executable, str(driver), "lint", "--config", "flow.toml", "--gate-untrusted"]

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(flow_root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=18,
        )
        result_text = completed.stdout.strip()
    except Exception:
        return 0

    if not result_text:
        return 0

    try:
        data = json.loads(result_text)
    except Exception:
        return 0

    status = data.get("status") or ""
    warnings = data.get("warnings") or []
    tail = data.get("tail") or ""
    reason = data.get("reason") or ""

    if status not in {"fail", "blocked", "timeout"} and not warnings:
        return 0

    lines = [f"[logicpilot] lint status after editing {Path(file_path).name}: {status or 'unknown'}"]
    if reason:
        lines.append(f"reason: {reason}")
    if warnings:
        lines.append("warnings:")
        lines.extend(f"  - {warning}" for warning in warnings[:5])
    if tail:
        lines.append("log tail:")
        lines.append(str(tail)[:1200])
    lines.append("[logicpilot] Review before synthesis; use /lp-tools for environment issues.")
    emit_context("PostToolUse", "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
