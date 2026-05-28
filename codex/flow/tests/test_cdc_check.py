"""Tests for the built-in cdc-check stage (v0.8 §5)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.cdc_check import (  # noqa: E402
    REQUIRED_CROSSING_KEYS,
    REQUIRED_TOP_KEYS,
    TRUTH_TABLE,
    run_cdc_check,
)


# --- helpers ----------------------------------------------------------------

def _write_inv(tmp_path: Path, content: dict | str) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    inv = docs / "cdc-inventory.json"
    if isinstance(content, dict):
        inv.write_text(json.dumps(content))
    else:
        inv.write_text(content)
    return inv


def _good_inventory() -> dict:
    return {
        "version": "1",
        "generated_by": "test",
        "generated_at": "2026-05-26T00:00:00Z",
        "top_module": "soc_top",
        "set_clock_groups_declared": True,
        "clocks": [
            {"name": "clk_a", "domain": "core"},
            {"name": "clk_b", "domain": "peripheral"},
        ],
        "crossings": [
            {
                "from_clock": "clk_a", "to_clock": "clk_b",
                "signal": "u_fifo.wr_ptr", "width": 5,
                "payload_kind": "bus", "synchronizer": "gray_counter",
                "verdict": "safe",
            }
        ],
    }


def _cfg(tmp_path: Path) -> dict:
    return {"_root": tmp_path}


# --- missing / parse error -------------------------------------------------

def test_missing_inventory_blocked(tmp_path: Path) -> None:
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "blocked"
    assert "not found" in out["reason"]


def test_json_parse_error_fails(tmp_path: Path) -> None:
    _write_inv(tmp_path, "{not valid json")
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert "parse error" in out["reason"]


def test_print_cmd_dry_run(tmp_path: Path) -> None:
    out = run_cdc_check(_cfg(tmp_path), print_cmd=True)
    assert out["status"] == "dry-run"


# --- shape validation -------------------------------------------------------

def test_missing_top_key_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    del inv["top_module"]
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_missing_top_key" for f in out["findings"])


def test_required_top_keys_constant_complete() -> None:
    """Drift detector — schema changes must update REQUIRED_TOP_KEYS."""
    expected = {"version", "generated_by", "generated_at",
                "top_module", "clocks", "crossings",
                "set_clock_groups_declared"}
    assert set(REQUIRED_TOP_KEYS) == expected


def test_required_crossing_keys_constant_complete() -> None:
    expected = {"from_clock", "to_clock", "signal",
                "payload_kind", "synchronizer", "verdict"}
    assert set(REQUIRED_CROSSING_KEYS) == expected


def test_wrong_version_warns_but_continues(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["version"] = "2"
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert any(f["rule"] == "cdc_unsupported_version" for f in out["findings"])


# --- happy path -------------------------------------------------------------

def test_good_inventory_passes(tmp_path: Path) -> None:
    _write_inv(tmp_path, _good_inventory())
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "pass"
    assert out["crossings_total"] == 1
    assert out["by_verdict"] == {"safe": 1, "unsafe": 0, "waived": 0}


def test_empty_crossings_with_clock_groups_passes(tmp_path: Path) -> None:
    """Single-clock or pre-integration → no crossings, no R6 fail."""
    inv = _good_inventory()
    inv["crossings"] = []
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "pass"


# --- R6: set_clock_groups_declared -----------------------------------------

def test_r6_clock_groups_undeclared_with_crossings_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["set_clock_groups_declared"] = False
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_clock_groups_not_declared" for f in out["findings"])


def test_r6_clock_groups_undeclared_but_no_crossings_passes(tmp_path: Path) -> None:
    """Empty crossings → R6 doesn't fire."""
    inv = _good_inventory()
    inv["set_clock_groups_declared"] = False
    inv["crossings"] = []
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "pass"


# --- truth table (R1-R3 combined) ------------------------------------------

def test_bus_x_2ff_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["synchronizer"] = "2ff"
    inv["crossings"][0]["stages"] = 2
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_truth_table_violation" for f in out["findings"])


def test_pulse_x_2ff_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "pulse"
    inv["crossings"][0]["synchronizer"] = "2ff"
    inv["crossings"][0]["stages"] = 2
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_truth_table_violation" for f in out["findings"])


def test_pulse_x_handshake_passes(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "pulse"
    inv["crossings"][0]["synchronizer"] = "handshake_req_ack"
    inv["crossings"][0]["cycles_to_settle"] = 6
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "pass"


def test_level_x_2ff_passes(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "level"
    inv["crossings"][0]["synchronizer"] = "2ff"
    inv["crossings"][0]["stages"] = 2
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "pass"


def test_unknown_payload_kind_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "nonsense"
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_unknown_payload_kind" for f in out["findings"])


# --- C4 special: synchronizer="none" ---------------------------------------

def test_none_synchronizer_with_safe_verdict_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["synchronizer"] = "none"
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_unprotected_crossing" for f in out["findings"])


def test_none_synchronizer_with_waived_verdict_passes(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["synchronizer"] = "none"
    inv["crossings"][0]["verdict"] = "waived"
    inv["crossings"][0]["rationale"] = "static config; clocks idle at writes"
    inv["crossings"][0]["evidence"] = {"file": "src/cfg.sv", "line": 12}
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "pass"


# --- R4 / R5: verdict-required fields --------------------------------------

def test_r4_unsafe_without_rationale_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["verdict"] = "unsafe"
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert any(f["rule"] == "cdc_unsafe_missing_rationale" for f in out["findings"])


def test_r5_waived_without_rationale_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["verdict"] = "waived"
    inv["crossings"][0]["evidence"] = {"file": "src/x.sv", "line": 1}
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert any(f["rule"] == "cdc_waived_missing_rationale" for f in out["findings"])


def test_r5_waived_without_evidence_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["verdict"] = "waived"
    inv["crossings"][0]["rationale"] = "waiver reason"
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert any(f["rule"] == "cdc_waived_missing_evidence" for f in out["findings"])


# --- crossings shape -------------------------------------------------------

def test_crossing_missing_required_key_fails(tmp_path: Path) -> None:
    inv = _good_inventory()
    del inv["crossings"][0]["verdict"]
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_crossing_missing_keys" for f in out["findings"])


# --- truth table data integrity --------------------------------------------

def test_truth_table_covers_all_payload_kinds() -> None:
    """Drift detector — adding a payload_kind must update TRUTH_TABLE."""
    assert set(TRUTH_TABLE.keys()) == {"pulse", "level", "bus", "reset_release"}


def test_truth_table_every_kind_has_waived_escape() -> None:
    """Every payload_kind must allow 'waived' as escape (per R5 docs)."""
    for kind, allowed in TRUTH_TABLE.items():
        assert "waived" in allowed, f"{kind}: missing 'waived' escape"


# --- conditional schema validation (mirrors schema's allOf) ----------------

def test_from_clock_equals_to_clock_fails(tmp_path: Path) -> None:
    """Same-domain register is not a crossing — must be flagged."""
    inv = _good_inventory()
    inv["crossings"][0]["to_clock"] = inv["crossings"][0]["from_clock"]
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_same_clock_not_crossing" for f in out["findings"])


def test_2ff_without_stages_fails(tmp_path: Path) -> None:
    """synchronizer='2ff' requires integer stages >= 2."""
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "level"
    inv["crossings"][0]["synchronizer"] = "2ff"
    # no 'stages' key at all
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_missing_stages" for f in out["findings"])


def test_3ff_with_stages_one_fails(tmp_path: Path) -> None:
    """stages must be >= 2 (a single flop isn't a synchronizer)."""
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "level"
    inv["crossings"][0]["synchronizer"] = "3ff"
    inv["crossings"][0]["stages"] = 1
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_missing_stages" for f in out["findings"])


def test_mux_synchronizer_requires_stages(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "level"
    inv["crossings"][0]["synchronizer"] = "mux_synchronizer"
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_missing_stages" for f in out["findings"])


def test_handshake_without_cycles_to_settle_fails(tmp_path: Path) -> None:
    """synchronizer='handshake_req_ack' requires integer cycles_to_settle >= 1."""
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "pulse"
    inv["crossings"][0]["synchronizer"] = "handshake_req_ack"
    # no cycles_to_settle
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_missing_cycles_to_settle" for f in out["findings"])


def test_conditional_checks_skipped_for_waived(tmp_path: Path) -> None:
    """A waived row may legitimately omit stages / cts (waiver carries the why)."""
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "level"
    inv["crossings"][0]["synchronizer"] = "2ff"
    inv["crossings"][0]["verdict"] = "waived"
    inv["crossings"][0]["rationale"] = "legacy IP block; stages unknown"
    inv["crossings"][0]["evidence"] = {"file": "rtl/legacy.v", "line": 1}
    # NO stages key
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    # Waived suppresses both truth-table AND conditional checks.
    assert not any(f["rule"] == "cdc_missing_stages" for f in out["findings"])


def test_stages_must_be_int_not_bool(tmp_path: Path) -> None:
    """Catch the Python isinstance(True, int) gotcha — bool is not a valid count."""
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "level"
    inv["crossings"][0]["synchronizer"] = "2ff"
    inv["crossings"][0]["stages"] = True  # noqa: E712 — testing the trap
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert any(f["rule"] == "cdc_missing_stages" for f in out["findings"])


# --- audit_engine field disclosure (v1.0+) --------------------------------

def test_audit_engine_default_is_regex(tmp_path: Path) -> None:
    """No --experimental-ast → regex path; field still present."""
    _write_inv(tmp_path, _good_inventory())
    out = run_cdc_check(_cfg(tmp_path))
    assert out["audit_engine"] == "regex"


def test_audit_engine_regex_when_flag_set_but_no_verible(tmp_path, monkeypatch) -> None:
    """Flag set, verible NOT on PATH → silent degrade to regex."""
    from logicpilot_flow import verible_client
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: None)
    _write_inv(tmp_path, _good_inventory())
    out = run_cdc_check(_cfg(tmp_path), experimental={"ast"})
    assert out["audit_engine"] == "regex"


def test_audit_engine_field_present_on_blocked(tmp_path: Path) -> None:
    """audit_engine must be on every status, including blocked (missing inventory)."""
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "blocked"
    assert "audit_engine" in out


def test_audit_engine_field_present_on_dry_run(tmp_path: Path) -> None:
    out = run_cdc_check(_cfg(tmp_path), print_cmd=True)
    assert out["audit_engine"] == "regex"


def test_audit_engine_field_present_on_parse_error(tmp_path: Path) -> None:
    _write_inv(tmp_path, "{ not json")
    out = run_cdc_check(_cfg(tmp_path))
    assert out["status"] == "fail"
    assert "audit_engine" in out


# --- R7 / R8 with mocked AST -----------------------------------------------

def _enable_ast(monkeypatch, drivers: list[tuple[str, str, int]]) -> None:
    """Pretend verible is installed and returns the given drivers."""
    from logicpilot_flow import verible_client
    monkeypatch.setattr(verible_client.shutil, "which", lambda _: "/fake/verible")
    # parse_file returns a sentinel dict; iter_clocked_drivers ignores
    # it and yields our scripted rows.
    monkeypatch.setattr(verible_client, "parse_file", lambda *a, **k: {"_": {"tree": {}}})
    monkeypatch.setattr(verible_client, "iter_clocked_drivers", lambda *a, **k: iter(drivers))


def _cfg_with_src(tmp_path: Path) -> dict:
    """Config that points cdc-check at a real SV file so source iteration finds something."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "design.sv").write_text("module m; endmodule\n")
    return {
        "_root": tmp_path,
        "project": {"src": ["src/**/*.sv"]},
    }


def test_audit_engine_verible_ast_when_flag_and_binary(tmp_path, monkeypatch) -> None:
    _enable_ast(monkeypatch, drivers=[])
    _write_inv(tmp_path, _good_inventory())
    out = run_cdc_check(_cfg_with_src(tmp_path), experimental={"ast"})
    assert out["audit_engine"] == "verible-ast"
    assert "ast_enumeration" in out


def test_r7_apparent_cdc_driver_not_in_inventory_fails(tmp_path, monkeypatch) -> None:
    """Two clock domains drive the same leaf; inventory has no row → R7 fail."""
    _enable_ast(monkeypatch, drivers=[
        ("clk_a", "ghost_sig", 100),
        ("clk_b", "ghost_sig", 200),
    ])
    _write_inv(tmp_path, _good_inventory())  # only covers wr_ptr
    out = run_cdc_check(_cfg_with_src(tmp_path), experimental={"ast"})
    assert out["status"] == "fail"
    rules = [f["rule"] for f in out["findings"]]
    assert "cdc_driver_missing_from_inventory" in rules


def test_r7_single_domain_driver_does_not_fail(tmp_path, monkeypatch) -> None:
    """One clock domain only → not a CDC, R7 does NOT fire."""
    _enable_ast(monkeypatch, drivers=[("clk_a", "local_flop", 10)])
    _write_inv(tmp_path, _good_inventory())
    out = run_cdc_check(_cfg_with_src(tmp_path), experimental={"ast"})
    assert out["status"] == "pass"
    rules = [f["rule"] for f in out["findings"]]
    assert "cdc_driver_missing_from_inventory" not in rules


def test_r7_driver_covered_by_inventory_passes(tmp_path, monkeypatch) -> None:
    """Two-domain driver IS in inventory → R7 doesn't fire."""
    _enable_ast(monkeypatch, drivers=[
        ("clk_a", "wr_ptr", 50),
        ("clk_b", "wr_ptr", 60),
    ])
    _write_inv(tmp_path, _good_inventory())  # has clk_a → clk_b, u_fifo.wr_ptr
    out = run_cdc_check(_cfg_with_src(tmp_path), experimental={"ast"})
    rules = [f["rule"] for f in out["findings"]]
    assert "cdc_driver_missing_from_inventory" not in rules


def test_r8_inventory_signal_not_in_rtl_warns(tmp_path, monkeypatch) -> None:
    """Inventory row references a signal AST can't find → R8 medium finding."""
    _enable_ast(monkeypatch, drivers=[("clk_a", "other_sig", 10)])
    inv = _good_inventory()
    # Inventory references wr_ptr; AST only sees other_sig — mismatch.
    _write_inv(tmp_path, inv)
    out = run_cdc_check(_cfg_with_src(tmp_path), experimental={"ast"})
    rules = [f["rule"] for f in out["findings"]]
    assert "cdc_inventory_signal_not_in_rtl" in rules


def test_ast_enumeration_summary_shape(tmp_path, monkeypatch) -> None:
    """ast_enumeration summary fields are stable across runs.

    Coverage is leaf-based (one count per unique signal leaf, not per
    (clock, leaf) pair) — see cdc_check._check_r7_r8 docstring.
    """
    _enable_ast(monkeypatch, drivers=[
        ("clk_a", "x", 1), ("clk_b", "x", 2),  # one apparent CDC leaf
        ("clk_a", "y", 3),                     # single-domain → not CDC
    ])
    _write_inv(tmp_path, _good_inventory())
    out = run_cdc_check(_cfg_with_src(tmp_path), experimental={"ast"})
    s = out["ast_enumeration"]
    assert s["enumerated_count"] == 3
    assert s["apparent_cdc_pairs"] == 1     # leaf 'x' only
    assert s["inventory_pairs"] >= 1
    assert s["r7_missing_pairs"] >= 0
    assert s["r8_stale_pairs"] >= 0


def test_enumerated_drivers_truncation(tmp_path, monkeypatch) -> None:
    """Big designs cap enumerated_drivers; warning row says so."""
    from logicpilot_flow import cdc_check as cdc_mod
    cap = cdc_mod._MAX_ENUMERATED_DRIVERS_IN_JSON
    many = [("clk_a", f"sig{i}", i) for i in range(cap + 10)]
    _enable_ast(monkeypatch, drivers=many)
    _write_inv(tmp_path, _good_inventory())
    out = run_cdc_check(_cfg_with_src(tmp_path), experimental={"ast"})
    assert len(out["enumerated_drivers"]) == cap
    assert any("truncated" in w for w in out.get("warnings", []))
