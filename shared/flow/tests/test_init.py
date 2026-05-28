"""Tests for /lp-init scaffolding (v0.7a §4a.1)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.init import (  # noqa: E402
    HDL_CHOICES,
    SCOPE_CHOICES,
    TARGET_CHOICES,
    run_init,
)


# --- minimal mode ----------------------------------------------------------

def test_minimal_mode_creates_core_files(tmp_path: Path) -> None:
    out = run_init(
        tmp_path,
        with_templates=False,
        hdl="systemverilog", target="open-fpga", scope="block", top="foo",
        interactive=False,
    )
    assert out["status"] == "pass"
    assert out["mode"] == "minimal"
    created = set(out["created"])
    # all 4 minimal files should be created
    assert any("flow.toml" in p for p in created)
    assert any(".gitignore" in p for p in created)
    assert any("src/.gitkeep" in p for p in created)
    assert any("tb/.gitkeep" in p for p in created)
    # docs/ files NOT created in minimal mode
    assert not any("docs/spec.md" in p for p in created)


def test_minimal_mode_flow_toml_content(tmp_path: Path) -> None:
    """flow.toml should reflect the chosen HDL extension and preset."""
    run_init(
        tmp_path, hdl="verilog", target="vivado", scope="block", top="my_ip",
        interactive=False,
    )
    flow = (tmp_path / "flow.toml").read_text()
    assert 'top = "my_ip"' in flow
    assert 'preset = "vivado"' in flow
    assert "*.v" in flow  # verilog → .v extension


# --- with-templates mode ---------------------------------------------------

def test_with_templates_creates_docs(tmp_path: Path) -> None:
    out = run_init(
        tmp_path, with_templates=True,
        hdl="systemverilog", target="open-fpga", scope="block", top="bar",
        interactive=False,
    )
    assert out["mode"] == "with-templates"
    created = set(out["created"])
    assert any("docs/spec.md" in p for p in created)
    assert any("docs/uarch.md" in p for p in created)
    assert any("docs/plan.md" in p for p in created)


def test_templates_contain_fill_placeholders(tmp_path: Path) -> None:
    """Plan-check rejects <<FILL: ...>> by design — verify the templates
    actually emit them so the agent immediately sees actionable failures."""
    run_init(
        tmp_path, with_templates=True,
        hdl="systemverilog", target="open-fpga", scope="block", top="bar",
        interactive=False,
    )
    for fname in ("spec.md", "uarch.md", "plan.md"):
        content = (tmp_path / "docs" / fname).read_text()
        assert "<<FILL:" in content, f"docs/{fname} missing FILL placeholders"


def test_plan_template_contains_checkbox(tmp_path: Path) -> None:
    """plan.md must have at least one - [ ] checkbox to satisfy plan-check."""
    run_init(
        tmp_path, with_templates=True,
        hdl="systemverilog", target="open-fpga", scope="block", top="x",
        interactive=False,
    )
    content = (tmp_path / "docs" / "plan.md").read_text()
    assert "- [ ]" in content


# --- no-overwrite safety ---------------------------------------------------

def test_pre_existing_files_are_preserved(tmp_path: Path) -> None:
    """Running --init on a non-empty repo must NOT overwrite existing files."""
    (tmp_path / "flow.toml").write_text("MY EXISTING CONFIG\n")
    out = run_init(
        tmp_path, hdl="verilog", target="open-fpga", scope="block", top="x",
        interactive=False,
    )
    assert "flow.toml" in " ".join(out["skipped"])
    assert (tmp_path / "flow.toml").read_text() == "MY EXISTING CONFIG\n"


def test_status_blocked_when_everything_already_exists(tmp_path: Path) -> None:
    """Second --init call with no changes → status=blocked, created=[]."""
    run_init(
        tmp_path, hdl="verilog", target="open-fpga", scope="block", top="x",
        interactive=False,
    )
    out = run_init(
        tmp_path, hdl="verilog", target="open-fpga", scope="block", top="x",
        interactive=False,
    )
    assert out["status"] == "blocked"
    assert out["created"] == []
    assert len(out["skipped"]) > 0


# --- choices validation ----------------------------------------------------

def test_invalid_hdl_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--hdl"):
        run_init(
            tmp_path, hdl="cobol", target="open-fpga", scope="block", top="x",
            interactive=False,
        )


def test_invalid_target_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--target"):
        run_init(
            tmp_path, hdl="verilog", target="mainframe", scope="block", top="x",
            interactive=False,
        )


def test_invalid_top_raises(tmp_path: Path) -> None:
    """top must be a legal HDL identifier."""
    with pytest.raises(ValueError, match="--top"):
        run_init(
            tmp_path, hdl="verilog", target="open-fpga", scope="block",
            top="123-bad",
            interactive=False,
        )


# --- interactive prompts via inputs={} -------------------------------------

def test_inputs_dict_skips_stdin(tmp_path: Path) -> None:
    """Tests inject choices via inputs={} to skip input()."""
    out = run_init(
        tmp_path,
        inputs={"hdl": "verilog", "target": "vivado",
                "scope": "block", "top": "ip0"},
        interactive=False,
    )
    assert out["choices"] == {
        "hdl": "verilog", "target": "vivado",
        "scope": "block", "top": "ip0",
    }


def test_default_values_when_non_interactive(tmp_path: Path) -> None:
    """Non-interactive + no flags + no inputs → falls back to defaults."""
    out = run_init(tmp_path, interactive=False)
    assert out["choices"]["hdl"] == "systemverilog"
    assert out["choices"]["target"] == "open-fpga"
    assert out["choices"]["scope"] == "block"
    assert out["choices"]["top"] == "top"


# --- choices catalogue stability -------------------------------------------

def test_known_choices_lists_have_expected_keys() -> None:
    """Drift-detector: choices catalogue should not shrink without a bump."""
    assert set(HDL_CHOICES) == {"verilog", "systemverilog", "vhdl", "mixed"}
    assert set(TARGET_CHOICES) == {"open-fpga", "vivado", "openlane", "front-only"}
    assert set(SCOPE_CHOICES) == {"block", "project"}


# --- next_step banner ------------------------------------------------------

def test_next_step_banner_for_minimal(tmp_path: Path) -> None:
    out = run_init(tmp_path, interactive=False)
    assert "src/" in out["next_step"]
    assert "lp-doctor" in out["next_step"]


def test_next_step_banner_for_with_templates(tmp_path: Path) -> None:
    out = run_init(tmp_path, with_templates=True, interactive=False)
    assert "<<FILL:" in out["next_step"]
    assert "lp-front" in out["next_step"]
