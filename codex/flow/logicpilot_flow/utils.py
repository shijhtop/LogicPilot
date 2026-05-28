"""LogicPilot hardware flow internals."""
from __future__ import annotations


import subprocess

def _coerce_timeout(value) -> float | None:
    if value in (None, "", 0):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _timeout_output(exc: subprocess.TimeoutExpired) -> str:
    parts = []
    for part in (exc.stdout, exc.stderr):
        if part is None:
            continue
        if isinstance(part, bytes):
            parts.append(part.decode(errors="replace"))
        else:
            parts.append(str(part))
    return "".join(parts)
