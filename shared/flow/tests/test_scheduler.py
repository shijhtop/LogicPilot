"""Tests for the Stage DAG + --jobs N scheduler.

Pure-function helpers (toposort, find_cycle, next_runnable,
hints_from_spec) are exercised exhaustively here. The executor
(run_dag) gets a smaller smoke set with a synchronous fake runner —
real subprocess work belongs in test_flow.py end-to-end tests.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logicpilot_flow.scheduler import (  # noqa: E402
    ResourceHints,
    _Ledger,
    find_cycle,
    hints_from_spec,
    next_runnable,
    run_dag,
    toposort,
)


# --- hints_from_spec -------------------------------------------------------

def test_hints_from_string_spec_returns_defaults() -> None:
    h = hints_from_spec("yosys -p ...")
    assert h == ResourceHints()


def test_hints_pull_all_fields() -> None:
    h = hints_from_spec({
        "expected_mem_gb": 12.5,
        "expected_cpu_cores": 4,
        "license_token": "vivado",
    })
    assert h.expected_mem_gb == 12.5
    assert h.expected_cpu_cores == 4
    assert h.license_token == "vivado"


def test_hints_negative_cpu_falls_back_to_default() -> None:
    """Hostile value silently degrades — config_schema warns the user."""
    h = hints_from_spec({"expected_cpu_cores": -2})
    assert h.expected_cpu_cores == 1


def test_hints_empty_license_token_is_none() -> None:
    h = hints_from_spec({"license_token": ""})
    assert h.license_token is None


# --- toposort --------------------------------------------------------------

def test_toposort_no_deps_preserves_order() -> None:
    assert toposort(["a", "b", "c"], {}) == ["a", "b", "c"]


def test_toposort_simple_chain() -> None:
    out = toposort(["a", "b", "c"], {"b": ["a"], "c": ["b"]})
    assert out == ["a", "b", "c"]


def test_toposort_diamond_is_deterministic() -> None:
    r"""  a
         / \
        b   c
         \ /
          d   ← b and c can interleave; tie-break = declared order."""
    out = toposort(["a", "b", "c", "d"], {"b": ["a"], "c": ["a"], "d": ["b", "c"]})
    assert out[0] == "a"
    assert out[3] == "d"
    assert set(out[1:3]) == {"b", "c"}


def test_toposort_ignores_unknown_predecessors() -> None:
    """A depends_on entry pointing at a stage not in our list is
    silently dropped (it's an 'already-satisfied' implicit gate)."""
    out = toposort(["b"], {"b": ["some_external_stage"]})
    assert out == ["b"]


def test_toposort_raises_on_cycle() -> None:
    import pytest
    with pytest.raises(ValueError, match="cycle"):
        toposort(["a", "b"], {"a": ["b"], "b": ["a"]})


# --- find_cycle ------------------------------------------------------------

def test_find_cycle_returns_none_when_acyclic() -> None:
    assert find_cycle(["a", "b"], {"b": ["a"]}) is None


def test_find_cycle_detects_two_node() -> None:
    cyc = find_cycle(["a", "b"], {"a": ["b"], "b": ["a"]})
    assert cyc is not None and set(cyc) == {"a", "b"}


def test_find_cycle_detects_three_node() -> None:
    cyc = find_cycle(["a", "b", "c"], {"a": ["c"], "b": ["a"], "c": ["b"]})
    assert cyc is not None and len(cyc) >= 3


def test_find_cycle_ignores_self_external() -> None:
    """Reference to stage outside the input set should NOT count as a cycle."""
    assert find_cycle(["a"], {"a": ["external"]}) is None


# --- next_runnable ---------------------------------------------------------

def _ledger(running=(), mem=0.0, cpu=0, licenses=()) -> _Ledger:
    return _Ledger(
        running=set(running),
        mem_in_use_gb=mem,
        cpu_in_use=cpu,
        license_holders=set(licenses),
    )


def test_next_runnable_picks_first_when_unconstrained() -> None:
    assert next_runnable(
        ["a", "b"], _ledger(), {}, available_mem_gb=64, cpu_count=8, jobs_cap=4
    ) == "a"


def test_next_runnable_returns_none_when_at_jobs_cap() -> None:
    assert next_runnable(
        ["a"], _ledger(running=["x", "y"]), {},
        available_mem_gb=64, cpu_count=8, jobs_cap=2,
    ) is None


def test_next_runnable_skips_mem_overshoot() -> None:
    hints = {
        "big": ResourceHints(expected_mem_gb=50),
        "small": ResourceHints(expected_mem_gb=2),
    }
    # 'big' would push us over 32 GB — try 'small' instead.
    assert next_runnable(
        ["big", "small"], _ledger(), hints,
        available_mem_gb=32, cpu_count=8, jobs_cap=4,
    ) == "small"


def test_next_runnable_mem_zero_hint_never_blocks() -> None:
    """0-GB hint = 'unknown / built-in / cheap'; always launchable."""
    hints = {"audit": ResourceHints(expected_mem_gb=0)}
    # Pretend the box has zero available memory; the 0-hint stage still runs.
    assert next_runnable(
        ["audit"], _ledger(), hints,
        available_mem_gb=0, cpu_count=4, jobs_cap=4,
    ) == "audit"


def test_next_runnable_cpu_throttle() -> None:
    hints = {
        "heavy": ResourceHints(expected_cpu_cores=8),
        "light": ResourceHints(expected_cpu_cores=1),
    }
    assert next_runnable(
        ["heavy", "light"], _ledger(cpu=6), hints,
        available_mem_gb=64, cpu_count=8, jobs_cap=4,
    ) == "light"


def test_next_runnable_serializes_license() -> None:
    hints = {
        "a": ResourceHints(license_token="vivado"),
        "b": ResourceHints(license_token="vivado"),
        "c": ResourceHints(license_token=None),
    }
    # 'a' already holds 'vivado'; only 'c' is launchable.
    assert next_runnable(
        ["b", "c"], _ledger(licenses=["vivado"]), hints,
        available_mem_gb=64, cpu_count=8, jobs_cap=4,
    ) == "c"


def test_next_runnable_returns_none_when_all_blocked() -> None:
    hints = {"a": ResourceHints(expected_mem_gb=99)}
    assert next_runnable(
        ["a"], _ledger(), hints,
        available_mem_gb=16, cpu_count=4, jobs_cap=4,
    ) is None


# --- run_dag (executor smoke) ----------------------------------------------

def _fast_runner(name: str) -> dict:
    """Synchronous fake runner — just returns pass."""
    return {"stage": name, "status": "pass"}


def test_run_dag_jobs_1_equivalence() -> None:
    """jobs=1 → still runs every stage, in topological order, halts on fail."""
    results, telem = run_dag(
        ["a", "b", "c"], {"b": ["a"], "c": ["b"]},
        hints={}, runner=_fast_runner,
        jobs=1,
        available_mem_gb_fn=lambda: 999, cpu_count_fn=lambda: 8,
    )
    assert [r["stage"] for r in results] == ["a", "b", "c"]
    assert telem["jobs"] == 1
    assert telem["peak_running"] == 1


def test_run_dag_jobs_2_runs_independent_in_parallel() -> None:
    """Two parallel stages should observe peak_running == 2."""
    # Use a runner that blocks briefly so concurrent runs overlap.
    barrier = threading.Barrier(2, timeout=2.0)

    def runner(name: str) -> dict:
        if name in ("a", "b"):
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
        return {"stage": name, "status": "pass"}

    results, telem = run_dag(
        ["a", "b"], depends_on={}, hints={}, runner=runner,
        jobs=2,
        available_mem_gb_fn=lambda: 999, cpu_count_fn=lambda: 8,
    )
    assert {r["stage"] for r in results} == {"a", "b"}
    assert telem["peak_running"] == 2


def test_run_dag_halt_on_failure_blocks_successors() -> None:
    """A failing predecessor must prevent its successor from launching."""
    launched: list[str] = []

    def runner(name: str) -> dict:
        launched.append(name)
        return {"stage": name, "status": "fail" if name == "a" else "pass"}

    results, _ = run_dag(
        ["a", "b"], {"b": ["a"]}, {}, runner,
        jobs=2,
        available_mem_gb_fn=lambda: 999, cpu_count_fn=lambda: 8,
    )
    assert launched == ["a"]
    assert [r["stage"] for r in results] == ["a"]


def test_run_dag_halt_blocks_parallel_success_successors() -> None:
    """Regression for codex review: when 'a' fails AND independent 'b'
    succeeds in the SAME scheduler batch, 'b's downstream 'c' must NOT
    launch. Pre-fix: the loop processed all done futures; the
    successful one released its successor into `ready`, and the
    forced-single-launch fallback then ran it despite halt_on_failure.
    """
    launched: list[str] = []

    def runner(name: str) -> dict:
        launched.append(name)
        return {
            "stage": name,
            "status": "fail" if name == "a" else "pass",
        }

    # a, b are independent (both top-level); c depends only on b.
    # With jobs=2 both a and b launch in the same scheduler tick; once
    # both complete, the halt from a must suppress c's release from b.
    results, _ = run_dag(
        ["a", "b", "c"], {"c": ["b"]}, {}, runner,
        jobs=2,
        available_mem_gb_fn=lambda: 999, cpu_count_fn=lambda: 8,
    )
    assert "c" not in launched, (
        f"c should not have launched after a failed in parallel batch; "
        f"got launched={launched}")
    assert {r["stage"] for r in results} == {"a", "b"}


def test_run_dag_halt_blocks_parallel_success_when_listed_first() -> None:
    """Regression for codex follow-up review: when the successful 'b' is
    listed BEFORE the failing 'a' (so its done-future is processed
    first), the previous fix's `if halted: continue` runs too late —
    b releases c into ready, then a sets halted, and the throttled
    fallback `not futures and ready` force-launches c despite the halt.

    Repro: stages=['b','a','c'], depends_on={'c':['b']}, jobs=2, 'a' fails.
    """
    launched: list[str] = []

    def runner(name: str) -> dict:
        launched.append(name)
        return {
            "stage": name,
            "status": "fail" if name == "a" else "pass",
        }

    results, _ = run_dag(
        ["b", "a", "c"], {"c": ["b"]}, {}, runner,
        jobs=2,
        available_mem_gb_fn=lambda: 999, cpu_count_fn=lambda: 8,
    )
    assert "c" not in launched, (
        f"c launched after a failed (order-flipped batch); "
        f"launched={launched}")
    assert {r["stage"] for r in results} == {"a", "b"}


def test_run_dag_halt_on_failure_disabled_runs_everything() -> None:
    launched: list[str] = []

    def runner(name: str) -> dict:
        launched.append(name)
        return {"stage": name, "status": "fail" if name == "a" else "pass"}

    results, _ = run_dag(
        ["a", "b"], {"b": ["a"]}, {}, runner,
        jobs=2,
        available_mem_gb_fn=lambda: 999, cpu_count_fn=lambda: 8,
        halt_on_failure=False,
    )
    assert set(launched) == {"a", "b"}
    assert {r["stage"] for r in results} == {"a", "b"}


def test_run_dag_force_serializes_when_all_throttled() -> None:
    """Stage with mem hint > available_mem_gb runs anyway (with telemetry)."""
    hints = {"huge": ResourceHints(expected_mem_gb=100)}
    results, telem = run_dag(
        ["huge"], {}, hints, _fast_runner,
        jobs=4,
        available_mem_gb_fn=lambda: 4, cpu_count_fn=lambda: 8,
    )
    assert results[0]["status"] == "pass"
    assert any(e["kind"] == "ready_stages_blocked" for e in telem["throttle_events"])


def test_run_dag_zero_jobs_rejected() -> None:
    import pytest
    with pytest.raises(ValueError, match="jobs"):
        run_dag(["a"], {}, {}, _fast_runner, jobs=0)


def test_run_dag_runner_exception_becomes_fail_row() -> None:
    """Safety net — a misbehaving runner shouldn't crash the scheduler."""
    def boom(name: str) -> dict:
        raise RuntimeError("intentional")
    results, _ = run_dag(
        ["a"], {}, {}, boom, jobs=2,
        available_mem_gb_fn=lambda: 999, cpu_count_fn=lambda: 8,
    )
    assert results[0]["status"] == "fail"
    assert "intentional" in results[0]["reason"]
