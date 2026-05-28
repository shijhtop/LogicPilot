"""Tests for the experimental feature flag registry (v0.10 §7.2.3)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.features import (  # noqa: E402
    REGISTRY,
    collect_active,
    flags_from_env,
    parse_flags,
    warnings_for_active,
)


# --- registry shape -------------------------------------------------------

def test_registry_has_ast_entry() -> None:
    assert "ast" in REGISTRY


def test_every_feature_has_valid_status() -> None:
    valid = {"stub", "preview", "default-pending", "removed-alias"}
    for name, f in REGISTRY.items():
        assert f.status in valid, f"{name}: bad status {f.status}"


def test_every_feature_has_required_fields() -> None:
    for name, f in REGISTRY.items():
        assert f.name == name
        assert f.description
        assert f.since


# --- parse_flags ----------------------------------------------------------

def test_parse_flags_picks_up_known_flag() -> None:
    flags, remaining = parse_flags(["--experimental-ast", "all"])
    assert flags == ["ast"]
    assert remaining == ["all"]


def test_parse_flags_passes_through_unknown() -> None:
    """Unknown experimental flags fall through so argparse errors normally."""
    flags, remaining = parse_flags(["--experimental-bogus", "all"])
    assert flags == []
    assert remaining == ["--experimental-bogus", "all"]


def test_parse_flags_preserves_non_experimental() -> None:
    flags, remaining = parse_flags(["--config", "x.toml", "all"])
    assert flags == []
    assert remaining == ["--config", "x.toml", "all"]


def test_parse_flags_empty_argv() -> None:
    flags, remaining = parse_flags([])
    assert flags == []
    assert remaining == []


# --- env vars -------------------------------------------------------------

def test_env_flag_picked_up(monkeypatch) -> None:
    monkeypatch.setenv("LOGICPILOT_EXPERIMENTAL_AST", "1")
    assert "ast" in flags_from_env()


def test_env_flag_truthy_values(monkeypatch) -> None:
    for val in ("1", "true", "True", "YES", "on"):
        monkeypatch.setenv("LOGICPILOT_EXPERIMENTAL_AST", val)
        assert "ast" in flags_from_env(), f"{val!r} should be truthy"


def test_env_flag_falsy_values(monkeypatch) -> None:
    for val in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("LOGICPILOT_EXPERIMENTAL_AST", val)
        assert "ast" not in flags_from_env(), f"{val!r} should be falsy"


def test_env_flag_unset(monkeypatch) -> None:
    monkeypatch.delenv("LOGICPILOT_EXPERIMENTAL_AST", raising=False)
    assert flags_from_env() == []


# --- collect_active -------------------------------------------------------

def test_collect_merges_cli_and_env(monkeypatch) -> None:
    monkeypatch.setenv("LOGICPILOT_EXPERIMENTAL_AST", "1")
    active, _ = collect_active(["all"])
    assert "ast" in active


# --- warnings_for_active --------------------------------------------------

def test_preview_warning_mentions_unstable_behaviour() -> None:
    """v1.0+: ast moved from stub→preview when Verible wiring landed.
    Warning text now signals that behaviour may shift between minor
    versions, not that the flag is a no-op."""
    out = warnings_for_active({"ast"})
    assert len(out) == 1
    assert "EXPERIMENTAL:ast" in out[0]
    assert "preview" in out[0].lower()
    assert "may change" in out[0].lower()


def test_ast_feature_is_preview_status() -> None:
    """Drift detector: if the ast feature changes status, the warning
    test above must update too."""
    assert REGISTRY["ast"].status == "preview"


def test_no_active_no_warnings() -> None:
    assert warnings_for_active(set()) == []
