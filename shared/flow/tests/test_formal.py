"""Tests for the built-in formal stage.

SBY isn't usually on CI runners, and the commercial backends never are.
Every test mocks shutil.which + subprocess.run with scripted SBY-style
stdout fixtures so the parser, dispatch, and envelope shape get full
coverage without touching a real prover.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow import formal  # noqa: E402
from logicpilot_flow.formal import run_formal  # noqa: E402


# --- helpers ---------------------------------------------------------------

def _cfg(tmp_path: Path, **formal_overrides) -> dict:
    """Minimal cfg with one SV source so _resolve_sources finds something."""
    src_dir = tmp_path / "rtl"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "dut.sv").write_text("module dut; endmodule\n")
    cfg = {
        "_root": tmp_path,
        "project": {"top": "dut", "src": ["rtl/*.sv"], "build_dir": "build"},
        "formal": {"mode": "prove", "depth": 20},
    }
    cfg["formal"].update(formal_overrides)
    return cfg


def _with_backend(monkeypatch, backend_path: dict[str, str]) -> None:
    """Mock shutil.which so only the named backends appear installed."""
    def fake_which(name):
        return backend_path.get(name)
    monkeypatch.setattr(formal.shutil, "which", fake_which)


def _with_sby_stdout(monkeypatch, stdout: str, returncode: int = 0) -> None:
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=returncode,
                                           stdout=stdout, stderr="")
    monkeypatch.setattr(formal.subprocess, "run", fake_run)


# --- experimental gate -----------------------------------------------------

def test_blocked_without_experimental_flag(tmp_path: Path) -> None:
    out = run_formal(_cfg(tmp_path))
    assert out["status"] == "blocked"
    assert "experimental-formal" in out["reason"]


def test_blocked_with_empty_experimental_set(tmp_path: Path) -> None:
    out = run_formal(_cfg(tmp_path), experimental=set())
    assert out["status"] == "blocked"
    assert "experimental-formal" in out["reason"]


def test_blocked_with_wrong_experimental_flag(tmp_path: Path) -> None:
    out = run_formal(_cfg(tmp_path), experimental={"ast"})
    assert out["status"] == "blocked"


# --- backend dispatch / no backend installed -------------------------------

def test_no_backend_installed_returns_blocked(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {})  # nothing on PATH
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    assert out["status"] == "blocked"
    assert "no formal backend" in out["reason"]
    assert set(out["missing"]) >= {"sby", "jaspergold", "vcf", "qverify"}
    assert "install_hint" in out


def test_pinned_missing_backend_blocked(tmp_path, monkeypatch) -> None:
    """`[formal].backend = "jaspergold"` but not installed → blocked
    citing exactly that one tool, not the whole list."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})  # sby is on PATH...
    cfg = _cfg(tmp_path)
    cfg["formal"]["backend"] = "jaspergold"  # ...but user pinned jasper
    out = run_formal(cfg, experimental={"formal"})
    assert out["status"] == "blocked"
    assert "jaspergold" in out["reason"]
    assert out["missing"] == ["jaspergold"]


# --- SBY backend: dry-run + config generation -----------------------------

def test_sby_dry_run_emits_cmd_and_config(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    out = run_formal(
        _cfg(tmp_path, mode="bmc", depth=30),
        print_cmd=True, experimental={"formal"},
    )
    assert out["status"] == "dry-run"
    assert out["tool"] == "sby"
    assert out["mode"] == "bmc"
    assert out["depth"] == 30
    assert "sby -f " in out["cmd"]
    assert "logicpilot_formal.sby" in out["cmd"]
    # The rendered .sby preview must contain the user's mode + depth
    assert "mode bmc" in out["sby_config_preview"]
    assert "depth 30" in out["sby_config_preview"]


def test_sby_mode_defaults_to_prove(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    cfg = _cfg(tmp_path)
    del cfg["formal"]["mode"]
    out = run_formal(cfg, print_cmd=True, experimental={"formal"})
    assert out["mode"] == "prove"


def test_sby_invalid_mode_falls_back_to_prove(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    out = run_formal(
        _cfg(tmp_path, mode="bogus"),
        print_cmd=True, experimental={"formal"},
    )
    assert "mode prove" in out["sby_config_preview"]


def test_sby_blocked_without_top(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    cfg = _cfg(tmp_path)
    del cfg["project"]["top"]
    out = run_formal(cfg, experimental={"formal"})
    assert out["status"] == "blocked"
    assert "top" in out["reason"]


def test_sby_blocked_when_no_sources(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    cfg = {
        "_root": tmp_path,
        "project": {"top": "dut", "src": ["nothing/*.sv"]},
        "formal": {},
    }
    out = run_formal(cfg, experimental={"formal"})
    assert out["status"] == "blocked"
    assert "zero" in out["reason"] or "no Verilog" in out["reason"].lower()


# --- SBY parser: PASS path -------------------------------------------------

_SBY_STDOUT_PASS = """\
SBY 14:34:55 [logicpilot_formal] engine_0 (smtbmc z3): starting process "yosys-smtbmc"
SBY 14:34:56 [logicpilot_formal] engine_0: ##   0:00:00  Reading model
SBY 14:34:57 [logicpilot_formal] engine_0: ##   0:00:01  Solver: z3
SBY 14:34:58 [logicpilot_formal] engine_0: ##   0:00:02  Checking assumptions in step 0..
SBY 14:34:59 [logicpilot_formal] engine_0: ##   0:00:03  Status: PASSED
SBY 14:34:59 [logicpilot_formal] DONE (PASS, rc=0)
"""


def test_sby_pass_envelope_shape(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_PASS, returncode=0)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    assert out["status"] == "pass"
    assert out["tool"] == "sby"
    assert out["mode"] == "prove"
    assert out["depth"] == 20
    assert out["engine_used"] == "smtbmc z3"
    assert out["properties"] == {"<all>": "PASS"}
    assert out["counterexamples"] == []
    assert out["summary"] == {"pass": 1, "fail": 0, "unknown": 0}
    assert "warnings" not in out


# --- SBY parser: FAIL path with counterexample -----------------------------

_SBY_STDOUT_FAIL = """\
SBY 14:34:55 [logicpilot_formal] engine_0 (smtbmc z3): starting process "yosys-smtbmc"
SBY 14:34:57 [logicpilot_formal] engine_0: ##   0:00:01  Solver: z3
SBY 14:34:58 [logicpilot_formal] engine_0: ##   0:00:02  BMC failed!
SBY 14:34:58 [logicpilot_formal] engine_0: ##   0:00:02  Assert failed in fifo: rtl/checks.sv:42 (fifo_full_empty_excl)
SBY 14:34:58 [logicpilot_formal] engine_0: ##   0:00:02  Writing trace to VCD file: engine_0/trace.vcd
SBY 14:34:58 [logicpilot_formal] engine_0: ##   0:00:02  Status: FAILED
SBY 14:34:58 [logicpilot_formal] DONE (FAIL, rc=2)
"""


def test_sby_fail_emits_counterexample(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_FAIL, returncode=2)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    assert out["status"] == "fail"
    assert out["properties"] == {"fifo_full_empty_excl": "FAIL"}
    assert len(out["counterexamples"]) == 1
    cex = out["counterexamples"][0]
    assert cex["property"] == "fifo_full_empty_excl"
    # Trace path is rebased to absolute under work_dir
    assert cex["trace"].endswith("engine_0/trace.vcd")
    assert out["summary"] == {"pass": 0, "fail": 1, "unknown": 0}
    assert any("FAIL" in w for w in out.get("warnings", []))


# --- SBY parser: unparseable / unknown -------------------------------------

_SBY_STDOUT_UNKNOWN = """\
SBY 14:34:55 [logicpilot_formal] engine_0 (smtbmc z3): starting process "yosys-smtbmc"
SBY 14:34:57 [logicpilot_formal] engine_0: ##   0:00:01  Solver: z3
SBY 14:34:58 [logicpilot_formal] engine_0: ##   0:00:02  Reached time limit
SBY 14:34:58 [logicpilot_formal] engine_0: ##   0:00:02  Status: UNKNOWN
SBY 14:34:58 [logicpilot_formal] DONE (UNKNOWN, rc=4)
"""


def test_sby_unknown_marks_fail_with_unknown_in_summary(tmp_path, monkeypatch) -> None:
    """UNKNOWN verdict shouldn't be sold as pass; classified as fail
    (caller may waive). The summary counts it under 'unknown' for
    inspection."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_UNKNOWN, returncode=4)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    assert out["status"] == "fail"  # UNKNOWN treated as failing default
    # Without backfill, properties={} and summary={0,0,0} which silently lies
    # about why the run failed. Verify the synthetic <all>=UNKNOWN was added.
    assert out["properties"] == {"<all>": "UNKNOWN"}
    assert out["summary"] == {"pass": 0, "fail": 0, "unknown": 1}


def test_sby_unparseable_log_does_not_crash(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, "totally unrelated text", returncode=0)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    # No DONE marker + returncode 0 → infer pass
    assert out["status"] == "pass"
    assert out["properties"] == {}
    assert out["counterexamples"] == []


# --- SBY parser: depth_hit extraction --------------------------------------

_SBY_STDOUT_FAIL_WITH_DEPTH = """\
SBY 14:34:55 [proj] engine_0 (smtbmc z3): starting process "yosys-smtbmc"
SBY 14:34:56 [proj] engine_0: ##   0:00:00  Checking assert in step 0..
SBY 14:34:56 [proj] engine_0: ##   0:00:00  Checking assert in step 1..
SBY 14:34:56 [proj] engine_0: ##   0:00:01  Checking assert in step 2..
SBY 14:34:57 [proj] engine_0: ##   0:00:01  Checking assert in step 5..
SBY 14:34:57 [proj] engine_0: ##   0:00:02  BMC failed at step 5
SBY 14:34:58 [proj] engine_0: Assert failed in fifo: rtl/checks.sv:42 (overflow_excl)
SBY 14:34:58 [proj] engine_0: Writing trace to VCD file: engine_0/trace.vcd
SBY 14:34:58 [proj] engine_0: Status: FAILED
SBY 14:34:58 [proj] DONE (FAIL, rc=2)
"""


def test_sby_depth_hit_extracted_from_explicit_marker(tmp_path, monkeypatch) -> None:
    """Counterexample should carry the BMC step at which the assertion failed."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_FAIL_WITH_DEPTH, returncode=2)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    assert out["status"] == "fail"
    assert len(out["counterexamples"]) == 1
    assert out["counterexamples"][0]["depth_hit"] == 5


_SBY_STDOUT_FAIL_STEP_FALLBACK = """\
SBY 14:34:55 [proj] engine_0 (smtbmc z3): starting process "yosys-smtbmc"
SBY 14:34:56 [proj] engine_0: Checking assert in step 0..
SBY 14:34:56 [proj] engine_0: Checking assert in step 1..
SBY 14:34:56 [proj] engine_0: Checking assert in step 2..
SBY 14:34:56 [proj] engine_0: Checking assert in step 3..
SBY 14:34:58 [proj] engine_0: Assert failed in m: rtl/m.sv:10 (p1)
SBY 14:34:58 [proj] engine_0: Writing trace to VCD file: engine_0/trace.vcd
SBY 14:34:58 [proj] DONE (FAIL, rc=2)
"""


def test_sby_depth_hit_fallback_to_largest_checking_step(tmp_path, monkeypatch) -> None:
    """Without an explicit 'BMC failed at step N', use the largest
    'Checking assert in step N' seen before the failure."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_FAIL_STEP_FALLBACK, returncode=2)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    assert out["counterexamples"][0]["depth_hit"] == 3


def test_sby_depth_hit_none_when_no_marker(tmp_path, monkeypatch) -> None:
    """Existing FAIL fixture has no step info — depth_hit stays None."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_FAIL, returncode=2)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    assert out["counterexamples"][0]["depth_hit"] is None


# --- [formal].properties scoping ------------------------------------------

_SBY_STDOUT_TWO_FAILS = """\
SBY 14:34:55 [proj] engine_0 (smtbmc z3): starting process "yosys-smtbmc"
SBY 14:34:58 [proj] engine_0: Assert failed in m: rtl/m.sv:10 (prop_a)
SBY 14:34:58 [proj] engine_0: Writing trace to VCD file: engine_0/trace_a.vcd
SBY 14:34:58 [proj] engine_0: Assert failed in m: rtl/m.sv:20 (prop_b)
SBY 14:34:58 [proj] engine_0: Writing trace to VCD file: engine_0/trace_b.vcd
SBY 14:34:58 [proj] DONE (FAIL, rc=2)
"""


def test_formal_properties_filter_narrows_envelope(tmp_path, monkeypatch) -> None:
    """[formal].properties = ['prop_a'] hides prop_b from properties + cex."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_TWO_FAILS, returncode=2)
    out = run_formal(
        _cfg(tmp_path, properties=["prop_a"]),
        experimental={"formal"},
    )
    assert set(out["properties"].keys()) == {"prop_a"}
    assert all(c["property"] == "prop_a" for c in out["counterexamples"])
    assert out["summary"] == {"pass": 0, "fail": 1, "unknown": 0}
    assert out["requested_properties"] == ["prop_a"]


def test_formal_properties_filter_warns_when_name_missing(tmp_path, monkeypatch) -> None:
    """Requested-but-not-found name → warning row + fail status."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_PASS, returncode=0)
    out = run_formal(
        _cfg(tmp_path, properties=["does_not_exist"]),
        experimental={"formal"},
    )
    # Top-level DONE(PASS) ignored — user asked for a specific prop we never saw.
    assert out["status"] == "fail"
    assert any("does_not_exist" in w for w in out["warnings"])


def test_formal_properties_empty_list_runs_everything(tmp_path, monkeypatch) -> None:
    """Empty list (the default) preserves the all-properties behaviour."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_TWO_FAILS, returncode=2)
    out = run_formal(_cfg(tmp_path, properties=[]), experimental={"formal"})
    assert set(out["properties"].keys()) == {"prop_a", "prop_b"}
    assert "requested_properties" not in out


def test_formal_properties_int_misconfig_does_not_crash(tmp_path, monkeypatch) -> None:
    """A misconfigured `properties = 42` in flow.toml must not crash the run.
    Coerce to no-scope (unfiltered) rather than throw TypeError."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_TWO_FAILS, returncode=2)
    out = run_formal(_cfg(tmp_path, properties=42), experimental={"formal"})
    # Treated as if properties was absent — all assertions reported.
    assert set(out["properties"].keys()) == {"prop_a", "prop_b"}
    assert "requested_properties" not in out


def test_formal_properties_dict_misconfig_does_not_crash(tmp_path, monkeypatch) -> None:
    """Same defensive coercion for dict mis-config."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_TWO_FAILS, returncode=2)
    out = run_formal(_cfg(tmp_path, properties={"a": True}), experimental={"formal"})
    assert set(out["properties"].keys()) == {"prop_a", "prop_b"}


# --- SBY parser: depth_hit nearest-marker correctness ---------------------

_SBY_STDOUT_TWO_FAILS_WITH_DEPTHS = """\
SBY 14:34:55 [proj] engine_0 (smtbmc z3): starting process "yosys-smtbmc"
SBY 14:34:56 [proj] engine_0: ##   0:00:00  BMC failed at step 3
SBY 14:34:56 [proj] engine_0: Assert failed in m: rtl/m.sv:10 (prop_a)
SBY 14:34:56 [proj] engine_0: Writing trace to VCD file: engine_0/trace_a.vcd
SBY 14:34:58 [proj] engine_0: ##   0:00:01  BMC failed at step 7
SBY 14:34:58 [proj] engine_0: Assert failed in m: rtl/m.sv:20 (prop_b)
SBY 14:34:58 [proj] engine_0: Writing trace to VCD file: engine_0/trace_b.vcd
SBY 14:34:58 [proj] DONE (FAIL, rc=2)
"""


def test_sby_depth_hit_uses_nearest_marker_per_failure(tmp_path, monkeypatch) -> None:
    """Multi-failure log: prop_b's depth_hit must be 7, not 3 (the latter
    is prop_a's). Earlier bug used `.search()` which always returned the
    first match — leading to every failure inheriting the first step."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_TWO_FAILS_WITH_DEPTHS, returncode=2)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    by_prop = {c["property"]: c["depth_hit"] for c in out["counterexamples"]}
    assert by_prop["prop_a"] == 3
    assert by_prop["prop_b"] == 7


# --- SBY timeout -----------------------------------------------------------

def test_sby_subprocess_timeout_returns_timeout(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})

    def boom(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=600)

    monkeypatch.setattr(formal.subprocess, "run", boom)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    assert out["status"] == "timeout"
    assert any("timed out" in w for w in out.get("warnings", []))


# --- Commercial backends: stubs --------------------------------------------

def test_jaspergold_picked_first_when_installed(tmp_path, monkeypatch) -> None:
    """Without a pin, the first backend in PATH-order wins. Confirm
    SBY beats commercial when both installed."""
    _with_backend(monkeypatch, {
        "sby": "/usr/bin/sby",
        "jaspergold": "/opt/cadence/jaspergold",
    })
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_PASS)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    assert out["tool"] == "sby"   # SBY wins because it's first in the probe list


def test_jaspergold_pin_dispatches_then_stubs(tmp_path, monkeypatch) -> None:
    """User pins jaspergold; we dispatch but return the 'parser stub' envelope."""
    _with_backend(monkeypatch, {"jaspergold": "/opt/cadence/jaspergold"})
    cfg = _cfg(tmp_path)
    cfg["formal"]["backend"] = "jaspergold"
    out = run_formal(cfg, experimental={"formal"})
    assert out["status"] == "blocked"
    assert out["tool"] == "jaspergold"
    assert "vendor-specific" in out["reason"]
    assert "parser is not yet implemented" in out["reason"]


def test_vcformal_dispatch_stub(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"vcf": "/opt/synopsys/vcf"})
    cfg = _cfg(tmp_path)
    cfg["formal"]["backend"] = "vcf"
    out = run_formal(cfg, experimental={"formal"})
    assert out["status"] == "blocked"
    assert out["tool"] == "vcf"


def test_questa_formal_dispatch_stub(tmp_path, monkeypatch) -> None:
    _with_backend(monkeypatch, {"qverify": "/opt/mentor/qverify"})
    cfg = _cfg(tmp_path)
    cfg["formal"]["backend"] = "qverify"
    out = run_formal(cfg, experimental={"formal"})
    assert out["status"] == "blocked"
    assert out["tool"] == "qverify"


# --- envelope contract guard ----------------------------------------------

def test_envelope_carries_required_fields_on_pass(tmp_path, monkeypatch) -> None:
    """Drift detector: agents rely on these fields existing."""
    _with_backend(monkeypatch, {"sby": "/usr/bin/sby"})
    _with_sby_stdout(monkeypatch, _SBY_STDOUT_PASS)
    out = run_formal(_cfg(tmp_path), experimental={"formal"})
    for required in (
        "stage", "status", "tool", "mode", "depth",
        "properties", "counterexamples", "summary",
    ):
        assert required in out, f"missing required envelope field: {required}"
