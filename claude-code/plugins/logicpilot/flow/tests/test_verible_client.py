"""Tests for verible_client (v1.0+ AST wiring).

verible-verilog-syntax is rarely installed in CI runners, so every test
that needs the AST mocks subprocess.run directly. The PATH-probe test
and the missing-binary test exercise the real code paths.
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow import verible_client  # noqa: E402


# --- ast_available ---------------------------------------------------------

def test_ast_available_returns_bool() -> None:
    """Always boolean, never raises, even when verible is missing."""
    assert isinstance(verible_client.ast_available(), bool)


def test_ast_available_false_when_binary_missing(monkeypatch) -> None:
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: None)
    assert verible_client.ast_available() is False


def test_ast_available_true_when_binary_present(monkeypatch) -> None:
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: "/usr/bin/verible-verilog-syntax")
    assert verible_client.ast_available() is True


# --- parse_file failure modes ---------------------------------------------

def test_parse_file_returns_none_when_binary_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: None)
    src = tmp_path / "x.sv"
    src.write_text("module m; endmodule\n")
    assert verible_client.parse_file(src) is None


def test_parse_file_returns_none_when_file_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: "/fake/verible")
    assert verible_client.parse_file(tmp_path / "does_not_exist.sv") is None


def test_parse_file_returns_none_on_subprocess_timeout(monkeypatch, tmp_path) -> None:
    src = tmp_path / "x.sv"
    src.write_text("module m; endmodule\n")
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: "/fake/verible")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="verible", timeout=10)

    monkeypatch.setattr(verible_client.subprocess, "run", fake_run)
    verible_client.clear_cache()
    assert verible_client.parse_file(src) is None


def test_parse_file_returns_none_on_nonzero_exit(monkeypatch, tmp_path) -> None:
    src = tmp_path / "x.sv"
    src.write_text("module m; endmodule\n")
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: "/fake/verible")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="syntax err")

    monkeypatch.setattr(verible_client.subprocess, "run", fake_run)
    verible_client.clear_cache()
    assert verible_client.parse_file(src) is None


def test_parse_file_returns_none_on_bad_json(monkeypatch, tmp_path) -> None:
    src = tmp_path / "x.sv"
    src.write_text("module m; endmodule\n")
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: "/fake/verible")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="not json", stderr="")

    monkeypatch.setattr(verible_client.subprocess, "run", fake_run)
    verible_client.clear_cache()
    assert verible_client.parse_file(src) is None


# --- parse_file happy path + cache ----------------------------------------

def _fake_ast_envelope(file_path: str) -> dict:
    """Minimal valid Verible-style envelope."""
    return {
        file_path: {
            "tree": {"tag": "kVerilogSource", "children": []},
            "rawTokens": [],
        }
    }


def test_parse_file_returns_parsed_dict(monkeypatch, tmp_path) -> None:
    src = tmp_path / "x.sv"
    src.write_text("module m; endmodule\n")
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: "/fake/verible")

    fake_json = json.dumps(_fake_ast_envelope(str(src.resolve())))

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_json, stderr="")

    monkeypatch.setattr(verible_client.subprocess, "run", fake_run)
    verible_client.clear_cache()
    ast = verible_client.parse_file(src)
    assert ast is not None
    assert isinstance(ast, dict)
    assert "tree" in next(iter(ast.values()))


def test_parse_file_caches_per_file(monkeypatch, tmp_path) -> None:
    """Second call with unchanged mtime must not re-spawn the subprocess."""
    src = tmp_path / "x.sv"
    src.write_text("module m; endmodule\n")
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: "/fake/verible")

    call_count = {"n": 0}
    fake_json = json.dumps(_fake_ast_envelope(str(src.resolve())))

    def fake_run(*args, **kwargs):
        call_count["n"] += 1
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_json, stderr="")

    monkeypatch.setattr(verible_client.subprocess, "run", fake_run)
    verible_client.clear_cache()
    verible_client.parse_file(src)
    verible_client.parse_file(src)
    assert call_count["n"] == 1


# --- iter_clocked_drivers --------------------------------------------------

def _build_always_ff_ast(
    file_path: str, clock: str, lhs_signal: str, lhs_line: int = 42
) -> dict:
    """Hand-built minimal Verible-shaped AST for one always_ff block.

    Real Verible emits dozens of intermediate nodes per construct; this
    keeps only the structure iter_clocked_drivers actually walks for.
    """
    return {
        file_path: {
            "tree": {
                "tag": "kVerilogSource",
                "children": [
                    {
                        "tag": "kAlwaysStatement",
                        "children": [
                            # Event control wraps @(posedge clock)
                            {
                                "tag": "kEventControl",
                                "children": [
                                    {"tag": "posedge"},
                                    {"tag": "SymbolIdentifier",
                                     "text": clock,
                                     "start": [1, 10]},
                                ],
                            },
                            # Assignment body: signal <= ...
                            {
                                "tag": "kNonblockingAssignmentStatement",
                                "children": [
                                    {
                                        "tag": "kLPValue",
                                        "children": [
                                            {"tag": "SymbolIdentifier",
                                             "text": lhs_signal,
                                             "start": [lhs_line, 4]},
                                        ],
                                    },
                                ],
                            },
                        ],
                    }
                ],
            }
        }
    }


def test_iter_clocked_drivers_handles_none() -> None:
    assert list(verible_client.iter_clocked_drivers(None)) == []
    assert list(verible_client.iter_clocked_drivers({})) == []


def test_iter_clocked_drivers_yields_single_assignment() -> None:
    ast = _build_always_ff_ast("/p/x.sv", clock="clk_a", lhs_signal="ptr", lhs_line=50)
    drivers = list(verible_client.iter_clocked_drivers(ast))
    assert drivers == [("clk_a", "ptr", 50)]


def test_iter_clocked_drivers_skips_block_without_edge() -> None:
    """always_comb (no posedge/negedge) → no drivers."""
    ast = {
        "/p/x.sv": {
            "tree": {
                "tag": "kVerilogSource",
                "children": [
                    {
                        "tag": "kAlwaysStatement",
                        "children": [
                            {"tag": "kEventControl", "children": [
                                {"tag": "SymbolIdentifier", "text": "a",
                                 "start": [1, 1]},
                            ]},
                            {"tag": "kBlockingAssignmentStatement", "children": [
                                {"tag": "kLPValue", "children": [
                                    {"tag": "SymbolIdentifier", "text": "y",
                                     "start": [2, 1]},
                                ]},
                            ]},
                        ],
                    },
                ],
            }
        }
    }
    assert list(verible_client.iter_clocked_drivers(ast)) == []


def test_iter_clocked_drivers_multiple_clock_domains() -> None:
    """Verify CDC-like AST: same signal driven in two clock domains."""
    ast = {
        "/p/x.sv": {
            "tree": {
                "tag": "kVerilogSource",
                "children": [
                    _build_always_ff_ast("/p/x.sv", "clk_a", "shared", 10)["/p/x.sv"]["tree"]["children"][0],
                    _build_always_ff_ast("/p/x.sv", "clk_b", "shared", 20)["/p/x.sv"]["tree"]["children"][0],
                ],
            }
        }
    }
    drivers = list(verible_client.iter_clocked_drivers(ast))
    assert ("clk_a", "shared", 10) in drivers
    assert ("clk_b", "shared", 20) in drivers


# --- iter_all_assignments (powers audit_ast.py) ----------------------------

def _build_comb_block_ast(file_path: str, lhs: str, line: int = 42) -> dict:
    """always_comb / always @(*) block. No edge keyword → kind='comb'."""
    return {
        file_path: {
            "tree": {
                "tag": "kVerilogSource",
                "children": [
                    {
                        "tag": "kAlwaysStatement",
                        "children": [
                            # Event control with no posedge/negedge — comb.
                            {"tag": "kEventControl", "children": []},
                            {"tag": "kBlockingAssignmentStatement", "children": [
                                {"tag": "kLPValue", "children": [
                                    {"tag": "SymbolIdentifier", "text": lhs,
                                     "start": [line, 4]},
                                ]},
                            ]},
                        ],
                    }
                ],
            }
        }
    }


def _build_continuous_assign_ast(file_path: str, lhs: str, line: int = 7) -> dict:
    return {
        file_path: {
            "tree": {
                "tag": "kVerilogSource",
                "children": [
                    {
                        "tag": "kContinuousAssignmentStatement",
                        "children": [
                            {"tag": "kReference", "children": [
                                {"tag": "SymbolIdentifier", "text": lhs,
                                 "start": [line, 2]},
                            ]},
                        ],
                    }
                ],
            }
        }
    }


def test_iter_all_assignments_yields_clocked_kind() -> None:
    ast = _build_always_ff_ast("/p/x.sv", "clk", "q", 10)
    rows = list(verible_client.iter_all_assignments(ast))
    assert rows == [("q", "clocked", 10)]


def test_iter_all_assignments_yields_comb_kind() -> None:
    ast = _build_comb_block_ast("/p/x.sv", "y", 12)
    rows = list(verible_client.iter_all_assignments(ast))
    assert rows == [("y", "comb", 12)]


def test_iter_all_assignments_yields_continuous_kind() -> None:
    ast = _build_continuous_assign_ast("/p/x.sv", "z", 5)
    rows = list(verible_client.iter_all_assignments(ast))
    assert rows == [("z", "continuous", 5)]


def test_iter_all_assignments_empty_on_none() -> None:
    assert list(verible_client.iter_all_assignments(None)) == []
    assert list(verible_client.iter_all_assignments({})) == []
