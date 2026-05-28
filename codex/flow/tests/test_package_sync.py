from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "sync_package.py").exists() and (parent / "shared" / "flow").exists():
            return parent
    raise AssertionError("could not find LogicPilot repository root")


def test_sync_package_is_the_flow_sync_entrypoint() -> None:
    root = _repo_root()
    sync_package = (root / "sync_package.py").read_text(encoding="utf-8")
    sync_skills = (root / "sync_skills.py").read_text(encoding="utf-8")

    assert "shared/flow is the canonical flow source" in sync_package
    assert "sync_package" in sync_skills


def test_platform_flow_copies_match_shared_flow() -> None:
    root = _repo_root()
    shared = root / "shared" / "flow"
    mirrors = [
        root / "codex" / "flow",
        root / "claude-code" / "plugins" / "logicpilot" / "flow",
    ]

    baseline = sorted(
        p.relative_to(shared)
        for p in shared.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
    )
    for mirror in mirrors:
        current = sorted(
            p.relative_to(mirror)
            for p in mirror.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
        )
        assert current == baseline
        for rel in baseline:
            assert (mirror / rel).read_bytes() == (shared / rel).read_bytes(), rel
