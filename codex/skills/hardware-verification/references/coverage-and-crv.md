# Coverage & Constrained-Random Verification

## Two kinds of coverage

- **Code coverage** (automatic): line, statement, branch, toggle, FSM-state/arc.
  Tells you what RTL was *exercised*. Necessary but weak — exercising a line
  isn't checking it.
- **Functional coverage** (you write it): did the *interesting scenarios* from
  the spec actually occur? Covergroups/coverpoints sample values and crosses
  (e.g., "every opcode × every addressing mode", "FIFO hit full and empty",
  "back-to-back then stalled"). This is what tells you the test plan was met.

The goal is **coverage closure**: every spec feature mapped to a coverage point,
and all points hit, with all checks passing.

## The critical rule

Coverage collected without comprehensive checking is meaningless, and a failed
test must not contribute coverage. Build and debug the checkers/scoreboard
first, *then* accumulate coverage. Otherwise you "cover" code that produced wrong
results.

## Constrained-random verification (CRV)

When the input space is too big to enumerate, randomize within legal
constraints, run many seeded iterations, and let functional coverage report what
was reached; tighten constraints or add directed tests to fill holes.

- In SystemVerilog: `rand`/`randc` fields + `constraint` blocks + `covergroup`.
- In Python/cocotb: the `cocotb-coverage` package (and `pyvsc`) provide
  covergroup-style functional coverage and constrained randomization, bringing
  CRV/MDV techniques to the open-source flow.

Two CRV styles: "classical" — start fully random, tighten constraints toward
coverage goals; or coverage-directed — feed back coverage holes to bias
generation. Either way, **seed and log** every run so a failure replays exactly.

## Putting it together (metric-driven verification)

1. Write the test plan: list features → checks → coverage points.
2. Build self-checking environment (drivers/monitors/scoreboard/assertions).
3. Run directed tests for the obvious cases; add CRV for large spaces.
4. Measure code + functional coverage; all checks must pass.
5. Analyze holes → add directed tests or adjust constraints → repeat to closure.
6. Treat unreachable coverage points as either dead code (remove) or
   waived-with-reason (document).
