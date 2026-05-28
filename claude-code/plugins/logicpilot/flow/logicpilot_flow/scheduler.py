"""Stage DAG scheduler with mem / CPU / license throttling.

Splits cleanly into two layers:

1. **Pure decision functions** (``toposort``, ``find_cycle``,
   ``next_runnable``): no I/O, no subprocesses, no clocks. Easy to
   unit-test without flakiness.

2. **Executor** (``run_dag``): wraps a ``ThreadPoolExecutor`` and a
   resource ledger. Calls the pure functions to decide what to launch
   next. The real subprocess work happens inside the worker callable
   the caller supplies — the executor only manages ordering and
   throttling.

Why a thread pool, not a process pool?
  Every stage delegates to ``subprocess.run`` (the actual EDA tool is
  the heavyweight). A thread pool is enough to run those subprocesses
  in parallel, sidesteps the cost of pickling stage state across
  process boundaries, and avoids the macOS spawn-method surprises.

Why stdlib only?
  Same zero-compiled-deps promise that kept ``sysinfo`` away from
  psutil. ``concurrent.futures`` + ``threading`` + ``time`` is enough.

Resource model:
  Each stage MAY declare ``expected_mem_gb`` / ``expected_cpu_cores`` /
  ``license_token`` in ``flow.toml``. The scheduler treats those as
  ADVISORY: a stage will not launch if doing so would exceed
  ``available_mem_gb()`` or ``cpu_count()``, and at most one running
  stage may hold any given license_token at a time. Missing hints
  default to 0 GB / 1 CPU core / no token — so legacy projects keep
  the previous "fire and pray" semantics.
"""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Iterable, Optional

from . import sysinfo


# --- Resource hints --------------------------------------------------------

@dataclass(frozen=True)
class ResourceHints:
    """Per-stage advisory throttle hints from ``flow.toml``.

    Missing fields default to "no constraint" — preserves legacy
    behaviour for any project that does not declare hints.
    """
    expected_mem_gb: float = 0.0
    expected_cpu_cores: int = 1
    license_token: Optional[str] = None


def hints_from_spec(spec: dict | str) -> ResourceHints:
    """Pull resource hints out of a stage spec dict.

    Flat-string specs and any spec missing a hint key get the
    no-constraint defaults.
    """
    if not isinstance(spec, dict):
        return ResourceHints()
    mem = spec.get("expected_mem_gb")
    cpu = spec.get("expected_cpu_cores")
    tok = spec.get("license_token")
    return ResourceHints(
        expected_mem_gb=float(mem) if isinstance(mem, (int, float)) else 0.0,
        expected_cpu_cores=int(cpu) if isinstance(cpu, int) and cpu > 0 else 1,
        license_token=str(tok) if isinstance(tok, str) and tok else None,
    )


# --- DAG topology (pure) ---------------------------------------------------

def toposort(stages: list[str], depends_on: dict[str, list[str]]) -> list[str]:
    """Kahn's-algorithm topological sort.

    Inputs:
      stages:      all stage names that must appear in the output.
      depends_on:  ``{stage: [pred, ...]}``. Predecessors not present
                   in ``stages`` are silently ignored — they act as
                   "implicit always-already-satisfied" gates so a
                   project can reference a built-in like ``audit``
                   that's auto-injected by the runner.

    Returns:
      A list of stages in an order where every predecessor precedes
      its dependent. Ties are broken by the original ``stages`` order
      so the output is deterministic.

    Raises:
      ValueError if the graph has a cycle (``find_cycle`` gives the
      same answer non-fatally).
    """
    in_set = set(stages)
    incoming: dict[str, int] = {s: 0 for s in stages}
    outgoing: dict[str, list[str]] = {s: [] for s in stages}
    for stage, preds in depends_on.items():
        if stage not in in_set:
            continue
        for p in preds:
            if p in in_set:
                incoming[stage] += 1
                outgoing[p].append(stage)
    # Stable order: walk `stages` and emit anything currently ready.
    ready: list[str] = [s for s in stages if incoming[s] == 0]
    order: list[str] = []
    while ready:
        # Pop the earliest-declared ready stage to keep determinism.
        s = ready.pop(0)
        order.append(s)
        for succ in outgoing[s]:
            incoming[succ] -= 1
            if incoming[succ] == 0:
                # Insert in original-position order.
                insert_at = len(ready)
                idx = stages.index(succ)
                for i, r in enumerate(ready):
                    if stages.index(r) > idx:
                        insert_at = i
                        break
                ready.insert(insert_at, succ)
    if len(order) != len(stages):
        raise ValueError(
            f"depends_on graph has a cycle (sorted {len(order)} of {len(stages)})"
        )
    return order


def find_cycle(
    stages: list[str], depends_on: dict[str, list[str]]
) -> Optional[list[str]]:
    """Return one cycle in the dependency graph, or None if acyclic.

    Used by the runner to surface a clean error instead of crashing
    on the toposort ValueError.
    """
    in_set = set(stages)
    color: dict[str, int] = {s: 0 for s in stages}  # 0=white, 1=gray, 2=black
    stack: list[str] = []

    def dfs(node: str) -> Optional[list[str]]:
        color[node] = 1
        stack.append(node)
        for nxt in depends_on.get(node, []):
            if nxt not in in_set:
                continue
            if color[nxt] == 1:
                # Found a cycle — slice from where we first saw nxt.
                start = stack.index(nxt)
                return stack[start:] + [nxt]
            if color[nxt] == 0:
                cyc = dfs(nxt)
                if cyc is not None:
                    return cyc
        color[node] = 2
        stack.pop()
        return None

    for s in stages:
        if color[s] == 0:
            cyc = dfs(s)
            if cyc is not None:
                return cyc
    return None


# --- Throttle decision (pure) ----------------------------------------------

@dataclass
class _Ledger:
    """Live counters tracked by the executor; pure-function inputs to next_runnable."""
    running: set[str] = field(default_factory=set)
    mem_in_use_gb: float = 0.0
    cpu_in_use: int = 0
    license_holders: set[str] = field(default_factory=set)


def next_runnable(
    ready: list[str],
    ledger: _Ledger,
    hints: dict[str, ResourceHints],
    *,
    available_mem_gb: float,
    cpu_count: int,
    jobs_cap: int,
) -> Optional[str]:
    """Pick the next stage to launch, or None to wait.

    Returns the FIRST stage in ``ready`` that fits all three caps
    (jobs / mem / cpu / license). First-fit is deterministic and
    matches the user's declared pipeline order.
    """
    if len(ledger.running) >= jobs_cap:
        return None
    for name in ready:
        h = hints.get(name, ResourceHints())
        # Memory: only block if hint is set AND would overshoot.
        if h.expected_mem_gb > 0 and (
            ledger.mem_in_use_gb + h.expected_mem_gb > available_mem_gb
        ):
            continue
        # CPU: never overcommit.
        if ledger.cpu_in_use + h.expected_cpu_cores > cpu_count:
            continue
        # License: at most one holder per token.
        if h.license_token and h.license_token in ledger.license_holders:
            continue
        return name
    return None


# --- Executor --------------------------------------------------------------

def run_dag(
    stages: list[str],
    depends_on: dict[str, list[str]],
    hints: dict[str, ResourceHints],
    runner: Callable[[str], dict],
    *,
    jobs: int,
    available_mem_gb_fn: Callable[[], float] = sysinfo.available_mem_gb,
    cpu_count_fn: Callable[[], int] = sysinfo.cpu_count,
    poll_interval_s: float = 0.05,
    halt_on_failure: bool = True,
) -> tuple[list[dict], dict]:
    """Run ``stages`` in topological order with up to ``jobs`` parallel.

    Inputs:
      stages:         declared pipeline order (also the deterministic
                      tie-breaker for ready set ordering).
      depends_on:     ``{stage: [pred, ...]}``. Cycles are caller's
                      problem — call ``find_cycle`` first.
      hints:          per-stage ``ResourceHints``. Missing entries
                      default to no-constraint.
      runner:         callable that synchronously runs one stage and
                      returns its result dict (same shape as
                      ``run_stage`` would produce).
      jobs:           max parallelism cap. Must be >= 1.
      halt_on_failure: when True, a fail/blocked/timeout stage stops
                      new launches; in-flight stages still run to
                      completion (their results are recorded).

    Returns:
      ``(results_in_completion_order, telemetry_dict)``.

    The caller is responsible for re-ordering results back into the
    declared pipeline order if that matters for downstream JSON.
    """
    if jobs < 1:
        raise ValueError("jobs must be >= 1")

    # Snapshot system limits once. CPU is stable; mem could change
    # mid-run, but re-checking on every decision creates false
    # starvation when other processes briefly spike. One snapshot per
    # run is the documented contract.
    available_mem = available_mem_gb_fn()
    cpus = cpu_count_fn()

    incoming = {s: 0 for s in stages}
    successors: dict[str, list[str]] = {s: [] for s in stages}
    in_set = set(stages)
    for stage, preds in depends_on.items():
        if stage not in in_set:
            continue
        for p in preds:
            if p in in_set:
                incoming[stage] += 1
                successors[p].append(stage)

    ready: list[str] = [s for s in stages if incoming[s] == 0]
    ledger = _Ledger()
    lock = Lock()
    results: list[dict] = []
    futures: dict[Future, tuple[str, ResourceHints]] = {}
    halted = False
    throttle_events: list[dict] = []
    peak_running = 0

    def _wrap(name: str) -> dict:
        # Run the actual stage. Exceptions are caller's contract — the
        # runner callable is expected to translate them to a result dict.
        return runner(name)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        while True:
            with lock:
                # Launch as many as we can right now.
                while not halted:
                    pick = next_runnable(
                        ready, ledger, hints,
                        available_mem_gb=available_mem,
                        cpu_count=cpus,
                        jobs_cap=jobs,
                    )
                    if pick is None:
                        break
                    h = hints.get(pick, ResourceHints())
                    ready.remove(pick)
                    ledger.running.add(pick)
                    ledger.mem_in_use_gb += h.expected_mem_gb
                    ledger.cpu_in_use += h.expected_cpu_cores
                    if h.license_token:
                        ledger.license_holders.add(h.license_token)
                    fut = pool.submit(_wrap, pick)
                    futures[fut] = (pick, h)
                    if len(ledger.running) > peak_running:
                        peak_running = len(ledger.running)
                if halted and not futures:
                    # Halt is already in effect and no in-flight stages
                    # remain. Drop everything still queued — those entries
                    # are successors that were released BEFORE halt in the
                    # same batch (or just queued by earlier ready). Letting
                    # the throttled-fallback below force-launch them would
                    # defeat halt_on_failure even after the halt fired.
                    break
                if not futures and not ready:
                    break  # everything done
                if not futures and ready:
                    # Nothing running but something ready means we hit a
                    # hard throttle (e.g. one stage needs more RAM than
                    # the box has). Record the event + run sequentially.
                    throttle_events.append({
                        "kind": "ready_stages_blocked",
                        "stages": list(ready),
                        "reason": "all candidates exceed mem/cpu/license caps; running serially",
                    })
                    forced = ready.pop(0)
                    ledger.running.add(forced)
                    fut = pool.submit(_wrap, forced)
                    futures[fut] = (forced, hints.get(forced, ResourceHints()))

            # Wait for in-flight stages to finish.
            #
            # In `halt_on_failure=True` mode (the default), we wait for
            # the ENTIRE current pool of in-flight stages to drain
            # before processing any done futures. This is the "wave"
            # parallel model: stages within a wave run in parallel, but
            # waves are serialised. The reason: with rolling parallel
            # (start the next as soon as ONE finishes), a fast
            # successful stage releases its successor into `ready`
            # BEFORE we observe that a slower sibling stage has failed,
            # and the next launch loop happily picks up the successor
            # — defeating halt_on_failure. Waiting for the whole wave
            # makes failure observation atomic with successor release.
            #
            # `halt_on_failure=False` keeps the original rolling
            # behaviour for maximum throughput when no halt semantic is
            # promised.
            done_futs = []
            while not done_futs:
                if halt_on_failure:
                    # Drain the pool fully before continuing.
                    if futures and all(f.done() for f in futures):
                        done_futs = list(futures)
                    else:
                        time.sleep(poll_interval_s)
                else:
                    done_futs = [f for f in futures if f.done()]
                    if not done_futs:
                        time.sleep(poll_interval_s)

            with lock:
                for f in done_futs:
                    name, h = futures.pop(f)
                    try:
                        res = f.result()
                    except Exception as exc:  # safety net; runner shouldn't raise
                        res = {
                            "stage": name,
                            "status": "fail",
                            "reason": f"scheduler caught exception: {exc!r}",
                        }
                    results.append(res)
                    ledger.running.discard(name)
                    ledger.mem_in_use_gb = max(0.0, ledger.mem_in_use_gb - h.expected_mem_gb)
                    ledger.cpu_in_use = max(0, ledger.cpu_in_use - h.expected_cpu_cores)
                    if h.license_token:
                        ledger.license_holders.discard(h.license_token)

                    if halt_on_failure and res.get("status") in (
                        "fail", "blocked", "timeout"
                    ):
                        halted = True
                        continue
                    # Once halted, refuse to release successors even for
                    # in-flight stages that completed successfully — letting
                    # them release would re-populate `ready` and the outer
                    # loop could launch downstream stages despite the halt.
                    # In-flight stages still run to completion (their
                    # results are recorded above); only the *graph
                    # progression* stops.
                    if halted:
                        continue
                    # Release any successors whose last dep just completed.
                    for succ in successors.get(name, []):
                        incoming[succ] -= 1
                        if incoming[succ] == 0:
                            # Preserve declared-pipeline order in `ready`.
                            insert_at = len(ready)
                            idx = stages.index(succ)
                            for i, r in enumerate(ready):
                                if stages.index(r) > idx:
                                    insert_at = i
                                    break
                            ready.insert(insert_at, succ)

    telemetry = {
        "jobs": jobs,
        "peak_running": peak_running,
        "available_mem_gb_snapshot": available_mem,
        "cpu_count_snapshot": cpus,
        "throttle_events": throttle_events,
    }
    return results, telemetry
