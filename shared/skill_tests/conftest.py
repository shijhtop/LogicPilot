"""Shared pytest fixtures for skill pressure tests.

The static layer parses each scenario's YAML front matter and matches
the listed guard strings against the canonical SKILL.md in shared/skills.
No external dependencies beyond the Python standard library + pytest.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "shared" / "skills"
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"


@dataclass(frozen=True)
class Scenario:
    path: Path
    target_skill: str
    name: str
    title: str
    guards: tuple[str, ...]
    gate_text: tuple[str, ...]

    @property
    def skill_md(self) -> Path:
        return SKILLS_ROOT / self.target_skill / "SKILL.md"


_FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _parse_yaml_lite(text: str) -> dict:
    """Minimal YAML parser for the small subset we use: scalars + string lists.

    Avoids a PyYAML dependency in CI. Supports:
        key: value
        key:
          - item1
          - item2
    Items may be quoted with double quotes; quotes are stripped.
    """
    out: dict = {}
    current_key: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if current_key is None:
                raise ValueError(f"list item without key: {raw!r}")
            value = line[4:].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            out.setdefault(current_key, []).append(value)
            continue
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                out[key] = []
                current_key = key
            else:
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                out[key] = value
                current_key = None
        else:
            raise ValueError(f"unexpected line in scenario front matter: {raw!r}")
    return out


def load_scenario(path: Path) -> Scenario:
    text = path.read_text(encoding="utf-8")
    m = _FRONT_MATTER.match(text)
    if not m:
        raise ValueError(f"{path.name}: missing YAML front matter")
    data = _parse_yaml_lite(m.group(1))
    required = ("target_skill", "scenario", "title")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"{path.name}: missing front-matter keys: {missing}")
    guards = tuple(data.get("guards") or ())
    gate_text = tuple(data.get("gate_text") or ())
    return Scenario(
        path=path,
        target_skill=str(data["target_skill"]),
        name=str(data["scenario"]),
        title=str(data["title"]),
        guards=guards,
        gate_text=gate_text,
    )


def discover_scenarios() -> list[Scenario]:
    if not SCENARIOS_DIR.is_dir():
        return []
    return sorted(
        (load_scenario(p) for p in SCENARIOS_DIR.glob("*.md")),
        key=lambda s: (s.target_skill, s.name),
    )


@pytest.fixture(scope="session")
def scenarios() -> list[Scenario]:
    return discover_scenarios()
