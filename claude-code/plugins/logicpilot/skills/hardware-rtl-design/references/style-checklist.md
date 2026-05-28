# RTL Pre-Commit Checklist

Run through this before handing RTL to simulation/synthesis.

## Latches & combinational completeness
- [ ] Every `always_comb`/`always @(*)` assigns all outputs on all paths
- [ ] Every `case` has a `default`
- [ ] No variable read before assigned in a comb block

## Width & literals
- [ ] All literals sized (`8'd0`, `16'hFFFF`)
- [ ] No unintended truncation/extension in assignments or concatenations
- [ ] Comparisons between same-width operands

## Sequential hygiene
- [ ] `<=` in clocked blocks, `=` in comb blocks (never mixed)
- [ ] One clock + one reset per clocked block
- [ ] Async reset (if used) on sensitivity list and synchronously released

## CDC
- [ ] Every signal crossing clock domains is synchronized (2FF / gray / FIFO)
- [ ] CDC paths constrained as false/max-delay in the constraints file

## Common sim-vs-synth traps
- `initial` blocks for state won't synthesize on most flows — use reset
- `#delay` is ignored by synthesis — never gate behavior on it
- `===`/`!==` (4-state) don't synthesize — use `==`/`!=`
- Inferred latch from a missing `else` is the #1 silent bug
- Reading `x`/`z` in RTL: fine in sim, undefined after synth
