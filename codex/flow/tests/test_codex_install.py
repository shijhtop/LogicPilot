from __future__ import annotations

import importlib.util
import json
import re
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
README_FILES = [ROOT / "README.md", ROOT / "README.en.md"]


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


def test_no_legacy_placeholder_install_wrappers():
    assert not (ROOT / "install.sh").exists()
    assert not (ROOT / "install.ps1").exists()


def test_stale_package_version_is_not_present():
    stale_version = ".".join(("0", "5", "1"))
    offenders = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
        and path.suffix != ".pyc"
        and stale_version in path.read_text(encoding="utf-8", errors="ignore")
    ]

    assert not offenders


def test_codex_marketplace_package_includes_driver_and_prompts():
    manifest = CODEX_PLUGIN / ".codex-plugin" / "plugin.json"
    assert manifest.exists()
    assert (CODEX_PLUGIN / "skills").is_dir()
    assert (CODEX_PLUGIN / "flow" / "logicpilot.py").is_file()
    assert (CODEX_PLUGIN / "prompts" / "lp-run.md").is_file()


def test_codex_manifest_has_default_prompts():
    manifest = json.loads(
        (CODEX_PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    default_prompts = manifest["interface"].get("defaultPrompt")

    assert isinstance(default_prompts, list)
    assert 1 <= len(default_prompts) <= 3
    assert all(isinstance(prompt, str) and 0 < len(prompt) <= 128 for prompt in default_prompts)


def test_readme_links_point_to_existing_repo_files():
    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for readme in README_FILES:
        links = link_re.findall(readme.read_text(encoding="utf-8"))
        broken = []
        for target in links:
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = target.split("#", 1)[0]
            if path and not (readme.parent / path).exists():
                broken.append(target)

        assert not broken


def test_readme_status_contract_matches_driver_terms():
    for readme in README_FILES:
        text = readme.read_text(encoding="utf-8")
        assert "skipped" in text
        assert "dry-run" in text
        assert "warn" in text
        assert " / skip / " not in text


def test_codex_docs_do_not_use_project_local_driver_as_only_default():
    files = list(PROMPTS.glob("*.md")) + [CODEX_AGENTS]
    offenders = [
        str(path.relative_to(ROOT))
        for path in files
        if 'LOGICPILOT_FLOW:-./codex/flow/logicpilot.py' in path.read_text(encoding="utf-8")
    ]

    assert not offenders
