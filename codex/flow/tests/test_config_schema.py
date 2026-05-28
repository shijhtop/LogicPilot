"""Tests for flow.toml schema validation (v0.7a §4a.4).

The validator catches structural typos in flow.toml that would otherwise
silently fall through to default-then-fail-much-later behavior:
- unknown top-level section (e.g. 'projct' instead of 'project')
- unknown preset name (e.g. 'yossys-nextpnr')

It is intentionally NOT a full schema enforcer — nested-field shapes are
checked at use time by the consumers (resolve_stage, run_plan_check).
This module only catches the high-leverage typos that did-you-mean can
fix in one line of human time.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.config_schema import (  # noqa: E402
    KNOWN_PIPELINE_PRESETS,
    KNOWN_TOP_KEYS,
    ValidationError,
    format_errors,
    validate,
)


# --- top-level key validation ------------------------------------------------

def test_empty_config_is_valid() -> None:
    """An empty TOML is valid (just no project info)."""
    assert validate({}) == []


def test_all_known_top_keys_valid() -> None:
    """A config exercising every known top-level section is valid."""
    cfg = {key: {} for key in KNOWN_TOP_KEYS}
    assert validate(cfg) == []


def test_underscore_internal_keys_ignored() -> None:
    """_-prefixed keys are load_config internals; they're never user-facing."""
    cfg = {"_root": "/tmp", "_stages": {}, "_pipeline": []}
    assert validate(cfg) == []


def test_unknown_top_key_reported() -> None:
    cfg = {"projct": {"top": "m"}}  # typo
    errs = validate(cfg)
    assert len(errs) == 1
    assert errs[0].path == "projct"
    assert "unknown top-level key" in errs[0].message


def test_unknown_top_key_close_match_suggested() -> None:
    """Typos within edit distance get a did-you-mean."""
    errs = validate({"projct": {}})
    assert errs[0].suggestion is not None
    assert "project" in errs[0].suggestion


def test_unknown_top_key_far_match_no_suggestion() -> None:
    """No suggestion for obvious junk — fabricating one is worse than silence."""
    errs = validate({"qqqqq_garbage": {}})
    assert errs[0].suggestion is None


def test_multiple_unknown_keys_each_reported() -> None:
    errs = validate({"projct": {}, "tolchain": {}})
    paths = {e.path for e in errs}
    assert paths == {"projct", "tolchain"}


# --- preset validation -------------------------------------------------------

def test_known_pipeline_preset_valid() -> None:
    for preset in KNOWN_PIPELINE_PRESETS:
        cfg = {"pipeline": {"preset": preset}}
        assert validate(cfg) == [], f"preset {preset!r} should be valid"


def test_unknown_pipeline_preset_reported() -> None:
    errs = validate({"pipeline": {"preset": "yossys-nextpnr"}})
    assert any(e.path == "pipeline.preset" for e in errs)
    target = next(e for e in errs if e.path == "pipeline.preset")
    assert "yosys-nextpnr" in (target.suggestion or "")


def test_unknown_toolchain_preset_reported() -> None:
    """Legacy [toolchain].preset gets the same treatment."""
    errs = validate({"toolchain": {"preset": "vivadooo"}})
    assert any(e.path == "toolchain.preset" for e in errs)
    target = next(e for e in errs if e.path == "toolchain.preset")
    assert "vivado" in (target.suggestion or "")


def test_empty_preset_string_ignored() -> None:
    """Empty preset = preset not set; treat as unset, not invalid."""
    assert validate({"pipeline": {"preset": ""}}) == []


def test_non_string_preset_not_validated() -> None:
    """preset = 123 (wrong type) is for the consumer to handle; we don't crash."""
    assert validate({"pipeline": {"preset": 123}}) == []


# --- type guards -------------------------------------------------------------

def test_non_dict_config_returns_root_error() -> None:
    errs = validate("not a dict")  # type: ignore[arg-type]
    assert len(errs) == 1
    assert errs[0].path == "<root>"


def test_pipeline_not_a_dict_does_not_crash() -> None:
    """[pipeline] = "string" is malformed but validator must not throw."""
    errs = validate({"pipeline": "not a table"})
    # We don't yet validate that pipeline must be a table — but no crash.
    assert isinstance(errs, list)


# --- formatting --------------------------------------------------------------

def test_format_errors_with_suggestion() -> None:
    errs = [ValidationError(path="projct", message="unknown", suggestion="Did you mean: project?")]
    out = format_errors(errs)
    assert out == ["projct: unknown — Did you mean: project?"]


def test_format_errors_without_suggestion() -> None:
    errs = [ValidationError(path="qqq", message="unknown")]
    out = format_errors(errs)
    assert out == ["qqq: unknown"]


def test_validation_error_is_frozen() -> None:
    """Immutable so cli + future callers can pass them around safely."""
    err = ValidationError(path="p", message="m")
    try:
        err.path = "other"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ValidationError must be frozen")


# --- CLI integration ---------------------------------------------------------

def test_cli_emits_config_warnings_on_typo(tmp_path: Path, capsys) -> None:
    """End-to-end: a flow.toml with a typo'd top-level section produces
    config_warnings in the JSON output."""
    import json

    from logicpilot_flow.cli import main

    flow_toml = tmp_path / "flow.toml"
    flow_toml.write_text(
        "[project]\ntop = \"m\"\n"
        "[toolchain]\npreset = \"yosys-nextpnr\"\n"
        "[projct]\nfoo = 1\n"  # typo: unknown top-level section
        "[tolchain]\nbar = 2\n"  # typo: another unknown section
    )

    main(["--list", "--config", str(flow_toml)])
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "config_warnings" in parsed
    joined = " ".join(parsed["config_warnings"])
    assert "projct" in joined
    assert "tolchain" in joined
    # did-you-mean suggestions visible to user
    assert "project" in joined
    assert "toolchain" in joined


def test_cli_preset_typo_caught_by_load_config(tmp_path: Path, capsys) -> None:
    """Preset typo is caught by load_config's existing sys.exit guard, not
    the schema validator. Documenting current behavior: load_config errors
    out before the validator runs. If we ever soften load_config, the
    validator will surface the typo via the regular config_warnings path."""
    import json
    import pytest

    from logicpilot_flow.cli import main

    flow_toml = tmp_path / "flow.toml"
    flow_toml.write_text(
        "[toolchain]\npreset = \"yossys-nextpnr\"\n"  # typo
    )

    with pytest.raises(SystemExit):
        main(["--list", "--config", str(flow_toml)])


def test_cli_omits_config_warnings_when_clean(tmp_path: Path, capsys) -> None:
    """Clean flow.toml → no config_warnings field in output (additive)."""
    import json

    from logicpilot_flow.cli import main

    flow_toml = tmp_path / "flow.toml"
    flow_toml.write_text(
        "[project]\ntop = \"m\"\n"
        "[toolchain]\npreset = \"yosys-nextpnr\"\n"
    )

    main(["--list", "--config", str(flow_toml)])
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "config_warnings" not in parsed
