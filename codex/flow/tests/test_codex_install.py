from __future__ import annotations

import importlib.util
from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "install.py").exists() and (parent / "codex" / "prompts").exists():
            return parent
    raise AssertionError("could not find LogicPilot repository root")


ROOT = _repo_root()
INSTALL_PY = ROOT / "install.py"
PROMPTS = ROOT / "codex" / "prompts"
CODEX_AGENTS = ROOT / "codex" / "AGENTS.md"
CODEX_PLUGIN = ROOT / "codex"


def _load_install_module():
    spec = importlib.util.spec_from_file_location("logicpilot_install", INSTALL_PY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_install_exposes_driver_under_codex_home(tmp_path, monkeypatch):
    install = _load_install_module()
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))

    assert install.install_codex()

    driver = tmp_path / "codex-home" / "logicpilot" / "flow" / "logicpilot.py"
    assert driver.exists()
    assert driver.is_file()


def test_codex_marketplace_package_includes_driver_and_prompts():
    manifest = CODEX_PLUGIN / ".codex-plugin" / "plugin.json"
    assert manifest.exists()
    assert (CODEX_PLUGIN / "skills").is_dir()
    assert (CODEX_PLUGIN / "flow" / "logicpilot.py").is_file()
    assert (CODEX_PLUGIN / "prompts" / "lp-run.md").is_file()


def test_codex_docs_do_not_use_project_local_driver_as_only_default():
    files = list(PROMPTS.glob("*.md")) + [CODEX_AGENTS]
    offenders = [
        str(path.relative_to(ROOT))
        for path in files
        if 'LOGICPILOT_FLOW:-./codex/flow/logicpilot.py' in path.read_text(encoding="utf-8")
    ]

    assert not offenders
