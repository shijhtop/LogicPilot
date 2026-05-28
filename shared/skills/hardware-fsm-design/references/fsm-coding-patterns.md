# FSM coding patterns

## Two-process FSM

Best default for readable RTL: one clocked state register plus one combinational
next-state/output block. Use defaults at the top of the combinational block.

## Three-process FSM

Three blocks: (1) state register, (2) next-state combinational logic,
(3) **output register keyed on `state_d` (next), not `state_q`**.

```systemverilog
always_ff @(posedge clk or negedge rst_n)
  if (!rst_n) {ready_o, done_o} <= 2'b00;
  else case (state_d)              // <-- next, so output FF + state FF clock together
    IDLE: {ready_o, done_o} <= 2'b10;
    BUSY: {ready_o, done_o} <= 2'b00;
    DONE: {ready_o, done_o} <= 2'b01;
  endcase
```

Because the output case keys on `state_d`, the output FF and the state FF
clock on the same edge — outputs are glitch-free, timed with state, and
incur **no extra cycle of latency** vs. combinational Moore outputs that
get sampled one delta after the state changes. Use when outputs leave the
block, drive timing-critical paths, cross clock domains, or must be
glitch-free.

## One-process FSM

**Avoid.** Code is 12–80 % longer for the same FSM; all outputs are forced
registered (no async Mealy outputs possible); next-state expressions sit
inside the case keyed on the *current* state register (`case (state)`
... `state <= NEXT_STATE`), which is read-then-write-same-signal — error
prone and hard to review.

Use two-process by default; use three-process when outputs must be
registered.

## Safe defaults

- `state_d = state_q;`
- outputs default to inactive values;
- side-effect enables default to `0`;
- counters/indices default to hold.

## State encoding notes

- FPGA one-hot can reduce decode depth but increases FF count.
- Binary reduces FF count but can increase decode logic.
- Encoding hints are tool-specific; always read the synthesis report to confirm
  extraction and encoding.
