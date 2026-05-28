"""Tests for AST-only audit rules (audit_ast.py).

verible isn't typically on CI runners, so every test mocks
verible_client. The rule logic is pure-functional once the
driver index is built, so the mocks just feed scripted assignment
tuples into iter_all_assignments.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow import audit_ast, verible_client  # noqa: E402


def _enable_ast(monkeypatch, assignments_per_file: dict[str, list[tuple[str, str, int]]]) -> None:
    """Pretend verible is installed; route parse_file/iter_all_assignments
    to scripted rows.

    Keyed by file STR so the same monkeypatch can hand back different
    rows for different files in a multi-file run.
    """
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: "/fake/verible")

    def fake_parse(p, **kwargs):
        # Return a sentinel; iter_all_assignments will dispatch on the
        # filename key inside the dict, but our mock ignores the AST
        # contents and reads from the closure.
        return {str(p): {"tree": {}, "_mock_file": str(p)}}

    def fake_iter(ast):
        # The ast dict has one entry keyed by the file path string.
        for fpath, _payload in ast.items():
            for row in assignments_per_file.get(fpath, []):
                yield row

    monkeypatch.setattr(verible_client, "parse_file", fake_parse)
    monkeypatch.setattr(verible_client, "iter_all_assignments", fake_iter)


def _make_src(tmp_path: Path, name: str) -> Path:
    """Write a placeholder SV file so Path.exists() etc. pass; contents
    don't matter because the parser is mocked."""
    p = tmp_path / name
    p.write_text("// stub\n")
    return p


# --- ast_available gate ---------------------------------------------------

def test_returns_empty_when_verible_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: None)
    src = _make_src(tmp_path, "a.sv")
    out = audit_ast.run_ast_rules([src], tmp_path)
    assert out == []


# --- ast_multi_driver -----------------------------------------------------

def test_single_driver_no_finding(monkeypatch, tmp_path: Path) -> None:
    src = _make_src(tmp_path, "a.sv")
    _enable_ast(monkeypatch, {
        str(src.resolve()): [("foo", "clocked", 10)],
    })
    out = audit_ast.run_ast_rules([src], tmp_path)
    assert out == []


def test_two_clocked_drivers_same_signal_flags_multi(monkeypatch, tmp_path: Path) -> None:
    src = _make_src(tmp_path, "a.sv")
    _enable_ast(monkeypatch, {
        str(src.resolve()): [
            ("foo", "clocked", 10),
            ("foo", "clocked", 30),
        ],
    })
    out = audit_ast.run_ast_rules([src], tmp_path)
    rules = [f["rule"] for f in out]
    assert "ast_multi_driver" in rules
    multi = next(f for f in out if f["rule"] == "ast_multi_driver")
    assert multi["severity"] == "high"
    assert "2 blocks" in multi["message"]
    assert multi["file"] == "a.sv"
    assert multi["line"] == 10


def test_two_comb_drivers_same_signal_flags_multi(monkeypatch, tmp_path: Path) -> None:
    src = _make_src(tmp_path, "a.sv")
    _enable_ast(monkeypatch, {
        str(src.resolve()): [
            ("bar", "comb", 5),
            ("bar", "comb", 25),
        ],
    })
    out = audit_ast.run_ast_rules([src], tmp_path)
    assert any(f["rule"] == "ast_multi_driver" for f in out)


def test_continuous_plus_always_flags_multi(monkeypatch, tmp_path: Path) -> None:
    """assign foo = ... ; AND always block driving foo → multi-driver."""
    src = _make_src(tmp_path, "a.sv")
    _enable_ast(monkeypatch, {
        str(src.resolve()): [
            ("x", "continuous", 3),
            ("x", "clocked", 22),
        ],
    })
    out = audit_ast.run_ast_rules([src], tmp_path)
    rules = [f["rule"] for f in out]
    assert "ast_multi_driver" in rules


def test_multi_file_drivers_collapse_by_leaf(monkeypatch, tmp_path: Path) -> None:
    """Same leaf name in different files = collapses (multi-driver
    finding fires). Documented trade-off per audit_ast.py docstring."""
    a = _make_src(tmp_path, "a.sv")
    b = _make_src(tmp_path, "b.sv")
    _enable_ast(monkeypatch, {
        str(a.resolve()): [("ready", "clocked", 7)],
        str(b.resolve()): [("ready", "clocked", 14)],
    })
    out = audit_ast.run_ast_rules([a, b], tmp_path)
    assert any(f["rule"] == "ast_multi_driver" for f in out)


# --- ast_clocked_vs_comb_mix ---------------------------------------------

def test_clocked_and_comb_mix_fires(monkeypatch, tmp_path: Path) -> None:
    """Same signal driven by both clocked and comb blocks → high severity."""
    src = _make_src(tmp_path, "bad.sv")
    _enable_ast(monkeypatch, {
        str(src.resolve()): [
            ("hybrid", "clocked", 10),
            ("hybrid", "comb", 50),
        ],
    })
    out = audit_ast.run_ast_rules([src], tmp_path)
    rules = [f["rule"] for f in out]
    assert "ast_clocked_vs_comb_mix" in rules
    mix = next(f for f in out if f["rule"] == "ast_clocked_vs_comb_mix")
    assert mix["severity"] == "high"
    assert "clocked fights comb" in mix["message"]


def test_two_clocked_only_does_not_fire_mix(monkeypatch, tmp_path: Path) -> None:
    """Multi-driver fires but mix does not — distinct conditions."""
    src = _make_src(tmp_path, "a.sv")
    _enable_ast(monkeypatch, {
        str(src.resolve()): [
            ("foo", "clocked", 10),
            ("foo", "clocked", 30),
        ],
    })
    out = audit_ast.run_ast_rules([src], tmp_path)
    rules = [f["rule"] for f in out]
    assert "ast_multi_driver" in rules
    assert "ast_clocked_vs_comb_mix" not in rules


def test_two_comb_only_does_not_fire_mix(monkeypatch, tmp_path: Path) -> None:
    src = _make_src(tmp_path, "a.sv")
    _enable_ast(monkeypatch, {
        str(src.resolve()): [
            ("bar", "comb", 5),
            ("bar", "comb", 25),
        ],
    })
    out = audit_ast.run_ast_rules([src], tmp_path)
    rules = [f["rule"] for f in out]
    assert "ast_multi_driver" in rules
    assert "ast_clocked_vs_comb_mix" not in rules


def test_continuous_plus_clocked_does_not_fire_mix(monkeypatch, tmp_path: Path) -> None:
    """continuous (assign) is not 'comb' in the kind sense — the
    rule specifically targets always_comb vs always_ff conflicts.
    Multi-driver still catches this combination."""
    src = _make_src(tmp_path, "a.sv")
    _enable_ast(monkeypatch, {
        str(src.resolve()): [
            ("x", "continuous", 3),
            ("x", "clocked", 22),
        ],
    })
    out = audit_ast.run_ast_rules([src], tmp_path)
    rules = [f["rule"] for f in out]
    assert "ast_multi_driver" in rules
    assert "ast_clocked_vs_comb_mix" not in rules


# --- integration with audit.py ---------------------------------------------

def test_audit_engine_verible_ast_invokes_ast_rules(monkeypatch, tmp_path: Path) -> None:
    """End-to-end: run_source_audit with experimental={"ast"} + Verible
    available → AST rules run on top of regex rules."""
    from logicpilot_flow.audit import run_source_audit
    from logicpilot_flow.config import _expand_globs  # noqa: F401

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "design.sv").write_text("module m; endmodule\n")

    _enable_ast(monkeypatch, {
        str((src_dir / "design.sv").resolve()): [
            ("conflict", "clocked", 10),
            ("conflict", "comb", 20),
        ],
    })

    cfg = {
        "_root": tmp_path,
        "project": {"src": ["src/**/*.sv"]},
    }
    out = run_source_audit(cfg, experimental={"ast"})
    assert out["audit_engine"] == "verible-ast"
    rules = [f["rule"] for f in out["findings"]]
    assert "ast_multi_driver" in rules
    assert "ast_clocked_vs_comb_mix" in rules


def test_regex_engine_does_not_invoke_ast_rules(monkeypatch, tmp_path: Path) -> None:
    """Without --experimental-ast (or without Verible) → AST rules do
    not run, even if a multi-driver bug exists."""
    from logicpilot_flow.audit import run_source_audit
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: None)

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "design.sv").write_text(
        "module m;\n"
        "  reg x;\n"
        "  always_ff @(posedge clk) x <= 1;\n"
        "  always_comb x = 0;\n"
        "endmodule\n"
    )

    cfg = {
        "_root": tmp_path,
        "project": {"src": ["src/**/*.sv"]},
    }
    out = run_source_audit(cfg)
    assert out["audit_engine"] == "regex"
    rules = [f["rule"] for f in out["findings"]]
    assert "ast_multi_driver" not in rules
    assert "ast_clocked_vs_comb_mix" not in rules
