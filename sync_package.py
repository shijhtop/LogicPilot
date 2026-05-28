"""sync_package.py — shared/flow is the canonical flow source.

Copies shared/flow to all platform mirror directories:
  - codex/flow
  - claude-code/plugins/logicpilot/flow

Run after any change to shared/flow. CI verifies mirrors are in sync.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SHARED = ROOT / "shared" / "flow"
MIRRORS = [
    ROOT / "codex" / "flow",
    ROOT / "claude-code" / "plugins" / "logicpilot" / "flow",
]

_SKIP = {"__pycache__", ".pytest_cache"}


def _files(root: Path) -> list[Path]:
    return [
        p for p in root.rglob("*")
        if p.is_file() and not any(s in p.parts for s in _SKIP)
    ]


def sync(verbose: bool = False) -> bool:
    ok = True
    for mirror in MIRRORS:
        shared_files = {p.relative_to(SHARED) for p in _files(SHARED)}
        for rel in shared_files:
            src = SHARED / rel
            dst = mirror / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or dst.read_bytes() != src.read_bytes():
                shutil.copy2(src, dst)
                if verbose:
                    print(f"  sync → {mirror.name}/{rel}")
        # Remove stale files in mirror
        for dst in _files(mirror):
            rel = dst.relative_to(mirror)
            if rel not in shared_files:
                dst.unlink()
                if verbose:
                    print(f"  remove {mirror.name}/{rel}")
    return ok


if __name__ == "__main__":
    verbose = "--quiet" not in sys.argv
    sync(verbose=verbose)
    if verbose:
        print("sync_package: done")
