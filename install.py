"""install.py — LogicPilot installer for Codex."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent


def install_codex() -> bool:
    """Install LogicPilot flow into $CODEX_HOME/logicpilot/flow/.

    Returns True if the driver was successfully installed.
    """
    codex_home = os.environ.get("CODEX_HOME")
    if not codex_home:
        return False
    dest = Path(codex_home) / "logicpilot" / "flow"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "codex" / "flow", dest, dirs_exist_ok=True)
    return (dest / "logicpilot.py").exists()


if __name__ == "__main__":
    if install_codex():
        print("install: codex OK")
    else:
        print("install: CODEX_HOME not set — skipping codex install")
