"""LogicPilot hardware flow internals."""
from __future__ import annotations


import os
from pathlib import Path

from .config import _project_root

def _trust_file_path() -> Path:
    """Machine-local trust list shared with the PostToolUse hook.

    A project is trusted by listing its absolute path (one per line) here, NOT
    by any file inside the repository — trust must never travel with a cloned
    repo. Override the location with LOGICPILOT_TRUST_FILE.
    """
    override = os.environ.get("LOGICPILOT_TRUST_FILE")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "logicpilot" / "trusted"

def _project_is_trusted(root: Path) -> bool:
    if os.environ.get("LOGICPILOT_TRUST_PROJECT") == "1":
        return True
    try:
        lines = _trust_file_path().read_text().splitlines()
    except OSError:
        return False
    trusted = {ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")}
    return str(root) in trusted
