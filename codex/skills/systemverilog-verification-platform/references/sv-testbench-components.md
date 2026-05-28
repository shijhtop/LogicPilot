# SystemVerilog testbench component roles

## Transaction

A transaction is an abstract operation such as a packet, bus read/write, FIFO
push/pop, or configuration command. Keep it small, printable, copyable, and
comparable.

## Generator / sequencer

Chooses the next transaction. It can be directed, randomized, coverage-guided, or
test-specific. It should not directly wiggle DUT pins.

## Driver

Consumes transactions and drives the interface protocol. It owns the physical
DUT stimulus timing and uses the interface/clocking block rules.

## Monitor

Observes interface activity and reconstructs transactions. It must not drive.
Monitors are the best place to trigger scoreboards and coverage sampling.

## Reference model

Predicts expected behavior. It may be simple SV code, a DPI C/C++ model, Python,
or a golden-vector database.

## Scoreboard

Compares observed DUT output against reference predictions. It reports exact
mismatches with transaction ID, time, expected, and actual values.

## Coverage collector

Samples semantic events after the monitor has observed a real transaction. Do
not sample speculative stimulus that may be rejected by backpressure.

## Concurrent assertion patterns (bind-friendly)

Wrap the boilerplate clock + reset prefix in a macro so the assertion text
reads as one line:

```systemverilog
`define assert_clk(arg) \
  assert property (@(posedge clk) disable iff (!rst_n) arg)

ERROR_FIFO_OVERFLOW_FORBIDDEN:
  `assert_clk(full |-> !wr_en)
```

Common operators:

| op | meaning |
|---|---|
| `|->` | overlapping implication — consequent same cycle |
| `|=>` | non-overlapping — consequent next cycle |
| `$past(s, N)` | value of `s` `N` cycles ago |
| `$rose(s)` / `$fell(s)` / `$stable(s)` | edge / stability detect |
| `$onehot(v)` / `$onehot0(v)` | one-hot check (0 allowed in `0` form) |

Always add `disable iff (!rst_n)` on concurrent assertions that sample
post-reset state. Immediate assertions only fire in simulation; concurrent
assertions also drive formal.

### Bind syntax + file partitioning

```systemverilog
bind <target_module> chk_<name> u_chk (.*);  // injects into every instance
bind <target_module>:<inst_path> chk_<name> u_chk (.*);  // single instance
```

`.*` only works when every checker port name matches a target net name
**exactly** — different names or sliced widths require explicit
`.port(net)`. In practice, explicit connections are safer for
non-trivial checkers.

Partition external SVA files by signal scope:

1. **Ports-only** assertions — survive synthesis intact.
2. **Ports + registered internals** — survive most optimization.
3. **Ports + combinational internals** — combinational internals get
   optimized away post-synth and break their assertions; keep these
   separate so the surviving suite is unambiguous.
