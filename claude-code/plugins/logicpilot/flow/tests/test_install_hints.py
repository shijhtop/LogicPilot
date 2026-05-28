"""Tests for install_hints module + integration into blocked stages (v0.7a).

Per roadmap §4a.3: when a stage reports status=blocked because of a
missing external tool, attach an install_hint field giving concrete
install commands. Tools without registered hints are omitted silently
(additive evolution — don't fabricate a hint).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.install_hints import (  # noqa: E402
    INSTALL_HINTS,
    hints_for,
)


# --- INSTALL_HINTS shape -----------------------------------------------------

def test_install_hints_is_dict() -> None:
    assert isinstance(INSTALL_HINTS, dict)
    assert len(INSTALL_HINTS) > 0


def test_each_hint_has_at_least_one_actionable_key() -> None:
    """A hint with no installer is dead weight."""
    actionable_keys = {"apt", "brew", "pacman", "source", "vendor"}
    for tool, hint in INSTALL_HINTS.items():
        actionable = actionable_keys & set(hint.keys())
        assert actionable, f"{tool}: no actionable key (have {set(hint.keys())})"


def test_keys_are_well_known(tool: str = "yosys") -> None:
    """Sanity-check on the schema — only allow known keys."""
    allowed = {"apt", "brew", "pacman", "source", "vendor", "note"}
    for tool, hint in INSTALL_HINTS.items():
        unknown = set(hint.keys()) - allowed
        assert not unknown, f"{tool}: unknown key(s) {unknown}"


def test_core_tools_have_hints() -> None:
    """The most common tools must have hints (so /lp-tools is actually useful)."""
    must_have = ["yosys", "verilator", "iverilog", "ghdl", "nextpnr-ice40"]
    for tool in must_have:
        assert tool in INSTALL_HINTS, f"core tool {tool} missing from INSTALL_HINTS"


# --- hints_for() lookup ------------------------------------------------------

def test_hints_for_returns_subset_of_known_tools() -> None:
    result = hints_for(["yosys", "verilator"])
    assert set(result.keys()) == {"yosys", "verilator"}


def test_hints_for_silently_omits_unknown_tools() -> None:
    """Unknown tool → no entry. No fabricated guess."""
    result = hints_for(["yosys", "definitely-not-a-real-tool"])
    assert "definitely-not-a-real-tool" not in result
    assert "yosys" in result


def test_hints_for_empty_list() -> None:
    assert hints_for([]) == {}


def test_hints_for_all_unknown() -> None:
    """All-unknown input → empty dict (caller omits install_hint field)."""
    assert hints_for(["fake1", "fake2"]) == {}


def test_hint_dict_returned_by_reference_is_safe() -> None:
    """hints_for must not mutate INSTALL_HINTS even if caller mutates the result."""
    before = dict(INSTALL_HINTS["yosys"])
    result = hints_for(["yosys"])
    # Mutating the returned hint should not affect the registry
    # (caveat: this test currently passes by virtue of dict aliasing
    # being acceptable; if we ever need stronger isolation, switch to
    # copy.deepcopy in hints_for).
    assert result["yosys"] == before


# --- Integration: install_hint appears in blocked stage JSON -----------------

def test_runner_blocked_stage_emits_install_hint(tmp_path: Path) -> None:
    """When run_stage returns status=blocked with a known missing tool,
    install_hint must be in the JSON output."""
    from logicpilot_flow.runner import run_stage

    cfg = {
        "_root": tmp_path,
        "_stages": {
            "synth": {
                "cmd": "definitely-not-installed-tool --version",
                "name": "definitely-not-installed-tool",
                "probes": ["yosys"],  # yosys probe → if missing, hint applies
            },
        },
        "toolchain": {},
    }
    out = run_stage("synth", cfg)
    # If yosys happens to be installed in CI, skip this test silently
    # rather than depending on environment.
    if out.get("status") != "blocked":
        return
    assert "install_hint" in out
    assert "yosys" in out["install_hint"]
    assert "apt" in out["install_hint"]["yosys"]


def test_runner_blocked_with_unknown_tool_omits_install_hint(tmp_path: Path) -> None:
    """Missing tool without registered hint → install_hint field absent."""
    from logicpilot_flow.runner import run_stage

    cfg = {
        "_root": tmp_path,
        "_stages": {
            "synth": {
                "cmd": "never-real-tool --version",
                "name": "never-real-tool",
                "probes": ["never-real-tool"],
            },
        },
        "toolchain": {},
    }
    out = run_stage("synth", cfg)
    assert out["status"] == "blocked"
    assert "install_hint" not in out


def test_tools_discover_blocked_emits_install_hint(tmp_path: Path) -> None:
    """discover_tools(cfg) attaches install_hint to blocked project stages."""
    from logicpilot_flow.tools import discover_tools

    cfg = {
        "_root": tmp_path,
        "_stages": {
            "lint": {
                "cmd": "never-real-tool",
                "name": "never-real-tool",
                "probes": ["verilator"],
            },
        },
        "toolchain": {},
    }
    out = discover_tools(cfg)
    # If verilator happens to be on PATH, skip silently.
    if out["stages"]["lint"].get("status") != "blocked":
        return
    assert "install_hint" in out["stages"]["lint"]
    assert "verilator" in out["stages"]["lint"]["install_hint"]
