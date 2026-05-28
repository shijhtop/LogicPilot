"""Tests for the built-in constraints stage."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logicpilot_flow.constraints_gen import run_constraints  # noqa: E402


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


def _cfg(tmp_path: Path, **overrides) -> dict:
    base: dict = {
        "_root": tmp_path,
        "project": {"top": "cdc_top", "build_dir": "build"},
    }
    base.update(overrides)
    return base


def _good_inventory() -> dict:
    return {
        "version": "1",
        "generated_by": "test",
        "top_module": "cdc_top",
        "set_clock_groups_declared": True,
        "clocks": [
            {"name": "wr_clk", "period_ns": 10.0, "domain": "producer"},
            {"name": "rd_clk", "period_ns": 27.0, "domain": "consumer"},
        ],
        "crossings": [
            {
                "from_clock": "wr_clk", "to_clock": "rd_clk",
                "signal": "u_fifo.wr_ptr_gray", "width": 4,
                "payload_kind": "bus", "synchronizer": "gray_counter",
                "verdict": "safe",
            },
            {
                "from_clock": "rd_clk", "to_clock": "wr_clk",
                "signal": "u_fifo.rd_ptr_gray", "width": 4,
                "payload_kind": "bus", "synchronizer": "gray_counter",
                "verdict": "safe",
            },
        ],
    }


# --- happy paths -----------------------------------------------------------

def test_writes_sdc_with_clocks_and_groups(tmp_path: Path) -> None:
    _write_inv(tmp_path, _good_inventory())
    out = run_constraints(_cfg(tmp_path))

    assert out["status"] == "pass"
    assert out["tool"] == "internal"
    assert out["sdc_path"] == "build/auto.sdc"
    assert out["summary"]["clocks_declared"] == 2
    assert out["summary"]["clock_groups_declared"] == 1  # one (wr_clk, rd_clk) pair
    # gray_counter is not a 2ff/3ff so no max_delay generated.
    assert out["summary"]["max_delays_declared"] == 0
    assert out["summary"]["false_paths_declared"] == 0

    sdc = (tmp_path / "build" / "auto.sdc").read_text()
    assert "create_clock -name wr_clk -period 10.000 [get_ports wr_clk]" in sdc
    assert "create_clock -name rd_clk -period 27.000 [get_ports rd_clk]" in sdc
    assert "set_clock_groups -asynchronous -group {rd_clk} -group {wr_clk}" in sdc
    assert "DO NOT EDIT BY HAND" in sdc


def test_max_delay_emitted_for_2ff_safe_crossing(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["payload_kind"] = "level"
    inv["crossings"][0]["synchronizer"] = "2ff"
    inv["crossings"][0]["stages"] = 2
    inv["crossings"][0]["evidence"] = {
        "file": "rtl/x.v", "line": 1, "module": "async_fifo"
    }
    _write_inv(tmp_path, inv)
    out = run_constraints(_cfg(tmp_path))

    assert out["status"] == "pass"
    assert out["summary"]["max_delays_declared"] == 1
    # The TODO placeholder warning surfaces in the envelope so the user
    # knows the SDC isn't sign-off ready by itself.
    assert out["summary"]["todo_placeholders"] == 1
    assert any("TODO" in w for w in out["warnings"])

    sdc = (tmp_path / "build" / "auto.sdc").read_text()
    # max_delay uses the source clock's period (wr_clk = 10ns).
    assert "set_max_delay 10.000" in sdc
    assert "u_fifo/wr_ptr_gray" in sdc  # signal → hier glob translation
    assert "<TODO:" in sdc  # destination instance left for the user
    assert "async_fifo" in sdc  # hint references the module from inventory


def test_false_path_for_waived_unprotected_crossing(tmp_path: Path) -> None:
    inv = _good_inventory()
    inv["crossings"][0]["synchronizer"] = "none"
    inv["crossings"][0]["verdict"] = "waived"
    inv["crossings"][0]["rationale"] = "static config; clocks idle at writes"
    inv["crossings"][0]["evidence"] = {"file": "src/cfg.sv", "line": 12}
    _write_inv(tmp_path, inv)
    out = run_constraints(_cfg(tmp_path))

    assert out["status"] == "pass"
    assert out["summary"]["false_paths_declared"] == 1

    sdc = (tmp_path / "build" / "auto.sdc").read_text()
    assert "waiver rationale: static config; clocks idle at writes" in sdc
    assert "set_false_path -through" in sdc


# --- fallback paths --------------------------------------------------------

def test_fallback_to_project_clock_mhz_when_no_inventory(tmp_path: Path) -> None:
    """Project with no CDC inventory still gets a single create_clock."""
    cfg = _cfg(tmp_path)
    cfg["project"]["clock_mhz"] = 50  # 20ns
    out = run_constraints(cfg)

    assert out["status"] == "pass"
    assert out["summary"]["clocks_declared"] == 1
    assert out["summary"]["clock_groups_declared"] == 0
    assert any("no CDC inventory" in w for w in out["warnings"])

    sdc = (tmp_path / "build" / "auto.sdc").read_text()
    assert "create_clock -name clk -period 20.000 [get_ports clk]" in sdc


def test_blocked_when_no_clocks_anywhere(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    out = run_constraints(cfg)
    assert out["status"] == "blocked"
    assert "no clocks declared" in out["reason"]


def test_dry_run_does_not_write_file(tmp_path: Path) -> None:
    _write_inv(tmp_path, _good_inventory())
    out = run_constraints(_cfg(tmp_path), print_cmd=True)
    assert out["status"] == "dry-run"
    assert not (tmp_path / "build" / "auto.sdc").exists()


# --- robustness ------------------------------------------------------------

def test_garbage_inventory_falls_back_with_warning(tmp_path: Path) -> None:
    _write_inv(tmp_path, "{ not json")
    cfg = _cfg(tmp_path)
    cfg["project"]["clock_mhz"] = 100
    out = run_constraints(cfg)
    # Falls back to project clock; flags the inventory parse error.
    assert out["status"] == "pass"
    assert any("could not be parsed" in w for w in out["warnings"])


def test_inventory_with_zero_period_skips_clock(tmp_path: Path) -> None:
    """Defensive: a malformed clock row must be dropped, not crash."""
    inv = _good_inventory()
    inv["clocks"].append({"name": "broken_clk", "period_ns": 0})
    _write_inv(tmp_path, inv)
    out = run_constraints(_cfg(tmp_path))
    assert out["summary"]["clocks_declared"] == 2  # broken_clk skipped


def test_same_clock_pair_does_not_emit_group(tmp_path: Path) -> None:
    """Defensive: cdc-check rejects same-clock 'crossings' upstream, but
    if one slipped through we must not emit `-group {x} -group {x}`."""
    inv = _good_inventory()
    inv["crossings"][0]["to_clock"] = inv["crossings"][0]["from_clock"]
    _write_inv(tmp_path, inv)
    out = run_constraints(_cfg(tmp_path))
    # Only the rd_clk↔wr_clk pair from crossings[1] survives.
    assert out["summary"]["clock_groups_declared"] == 1


def test_custom_output_path_respected(tmp_path: Path) -> None:
    _write_inv(tmp_path, _good_inventory())
    cfg = _cfg(tmp_path, constraints={"output": "constraints/my.sdc"})
    out = run_constraints(cfg)
    assert out["status"] == "pass"
    assert out["sdc_path"] == "constraints/my.sdc"
    assert (tmp_path / "constraints" / "my.sdc").exists()


def test_envelope_contains_tail_with_last_lines(tmp_path: Path) -> None:
    _write_inv(tmp_path, _good_inventory())
    out = run_constraints(_cfg(tmp_path))
    # `tail` mirrors the last ≤ 25 lines of the SDC so report stage can show it.
    assert "set_clock_groups" in out["tail"] or "create_clock" in out["tail"]


# --- safe-mode path confinement (P1: codex review) -----------------------

def test_safe_mode_rejects_absolute_output_path(tmp_path: Path) -> None:
    """[constraints].output = '/etc/passwd' must be blocked in safe mode."""
    _write_inv(tmp_path, _good_inventory())
    cfg = _cfg(tmp_path, constraints={"output": "/tmp/should_not_be_written.sdc"})
    cfg["_safe_preset_only"] = True
    out = run_constraints(cfg)
    assert out["status"] == "blocked"
    assert "safe-preset mode" in out["reason"]
    # No file written anywhere.
    assert not Path("/tmp/should_not_be_written.sdc").exists()


def test_safe_mode_rejects_parent_traversal(tmp_path: Path) -> None:
    """[constraints].output = '../../foo.sdc' must be blocked in safe mode."""
    _write_inv(tmp_path, _good_inventory())
    cfg = _cfg(tmp_path, constraints={"output": "../../escape.sdc"})
    cfg["_safe_preset_only"] = True
    out = run_constraints(cfg)
    assert out["status"] == "blocked"
    assert "safe-preset mode" in out["reason"]


def test_safe_mode_allows_in_root_relative_paths(tmp_path: Path) -> None:
    """Relative paths under the project root must still work in safe mode."""
    _write_inv(tmp_path, _good_inventory())
    cfg = _cfg(tmp_path, constraints={"output": "build/safe.sdc"})
    cfg["_safe_preset_only"] = True
    out = run_constraints(cfg)
    assert out["status"] == "pass"
    assert (tmp_path / "build" / "safe.sdc").exists()


def test_trusted_mode_permits_absolute_output(tmp_path: Path) -> None:
    """Without safe mode, absolute output paths are honored (trusted run)."""
    _write_inv(tmp_path, _good_inventory())
    out_path = tmp_path / "elsewhere" / "abs.sdc"
    cfg = _cfg(tmp_path, constraints={"output": str(out_path)})
    # _safe_preset_only NOT set (falsy)
    out = run_constraints(cfg)
    assert out["status"] == "pass"
    assert out_path.exists()


def test_safe_mode_handles_mutual_symlink_loop(tmp_path: Path) -> None:
    """Two symlinks pointing at each other (a→b, b→a) must also be
    caught. Python 3.13+ regression: `resolve(strict=False)` silently
    returns on mutual loops on the newer interpreter. The OS-stat
    based detection must catch both shapes uniformly."""
    _write_inv(tmp_path, _good_inventory())
    (tmp_path / "a").symlink_to("b")
    (tmp_path / "b").symlink_to("a")
    cfg = _cfg(tmp_path, constraints={"output": "a/auto.sdc"})
    cfg["_safe_preset_only"] = True

    out = run_constraints(cfg)
    assert out["status"] == "blocked"
    assert "loop" in out["reason"].lower()


def test_safe_mode_handles_symlink_loop_gracefully(tmp_path: Path) -> None:
    """Regression for codex round-3 review: an untrusted project that
    sets `[constraints].output = "loop/auto.sdc"` where `loop → loop`
    used to crash with RuntimeError('Symlink loop') during
    `resolve(strict=False)`. The except only caught ValueError, so safe
    mode became a DoS vector — an attacker could prevent any
    constraints stage from running by symlinking a single file.
    Now caught and reported as `status: blocked`."""
    _write_inv(tmp_path, _good_inventory())
    # Self-referential symlink: loop → loop.
    (tmp_path / "loop").symlink_to("loop")
    cfg = _cfg(tmp_path, constraints={"output": "loop/auto.sdc"})
    cfg["_safe_preset_only"] = True

    # Must NOT raise — must return a controlled envelope.
    out = run_constraints(cfg)
    assert out["status"] == "blocked"
    assert "symlink loop" in out["reason"].lower(), (
        f"reason should mention symlink loop; got {out['reason']}")


def test_safe_mode_rejects_symlinked_output(tmp_path: Path) -> None:
    """Regression for codex follow-up review: lexical "no abs / no `..`"
    check still let `[constraints].output = "link/auto.sdc"` slip
    through when `link` was a symlink to e.g. `/etc/`. The resolve()
    pass walks symlinks and rejects."""
    _write_inv(tmp_path, _good_inventory())
    # Set up: an "escape" directory OUTSIDE the project root, and a
    # symlink inside the project pointing at it.
    escape_dir = tmp_path.parent / "outside_root"
    escape_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "link").symlink_to(escape_dir, target_is_directory=True)

    cfg = _cfg(tmp_path, constraints={"output": "link/auto.sdc"})
    cfg["_safe_preset_only"] = True
    out = run_constraints(cfg)
    assert out["status"] == "blocked", (
        f"symlinked output not rejected; envelope was {out}")
    assert "outside the project root" in out["reason"] or "resolves outside" in out["reason"]
    # CRITICAL: nothing was actually written outside the root.
    assert not (escape_dir / "auto.sdc").exists()
