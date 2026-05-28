# SystemVerilog procedural blocks and FSMs

## Procedural intent

- `always_ff`: sequential storage; one clock edge and optional reset.
- `always_comb`: pure combinational logic; no delay, event control, or wait.
- `always_latch`: intentional latch only; document why a latch is required.

## Assignment discipline

- Sequential logic: nonblocking `<=`.
- Combinational logic: blocking `=`.
- Do not mix assignment types in one procedural block.
- Driving one variable from multiple procedural blocks is a **race** —
  the SV scheduler does not order events in the same Active region across
  blocks. `always_ff` / `always_comb` / `always_latch` are the
  tool-enforced single-driver checks.

## SV scheduling regions (the why behind the rules)

Each time-slot is divided into ordered regions. The main ones that matter
for race avoidance:
**Preponed → Active → Inactive → NBA → Observed → Reactive → Re-NBA →
Postponed** (the LRM defines additional Pre / Post sub-regions; for RTL
review only the main flow matters).

| Region | Used by |
|---|---|
| Preponed | assertion sampling (stable pre-edge values) |
| Active | RTL `=` / non-`<=` blocks, `assign` |
| NBA | RTL `<=` LHS commits |
| Observed | concurrent assertion evaluation |
| Reactive / Re-NBA | TB `program` block + `clocking` block |

Why the rules work: RTL uses Active + NBA (`<=`); TB in a `program` block
runs in Reactive + Re-NBA, automatically one step *after* RTL — eliminating
TB↔RTL race without `#1`. Assertions sample Preponed (pre-edge) values, so
they see exactly what the FF latched.

**`#0` is a race patch, not a fix** — it schedules into the same time-slot's
Inactive region, which is still *before* NBA, so it cannot order against
`<=` updates.

## Clock generator pattern

```systemverilog
logic clk;
initial begin clk <= 0; forever #(CYCLE/2) clk = ~clk; end
```

- Put the clock generator in a `module` (top), not a `program` — clocks
  driven from `program` go through Re-NBA, which adds an extra delta on
  every edge.
- `clk <= 0` (NBA) at time 0 fires after all `initial` start, so there's
  no time-0 negedge race. Avoid `bit clk = 1;` — vendor behavior at
  time 0 varies.

## Tasks and functions

- Use `automatic` for reusable helper tasks/functions unless static storage is
  intentionally required.
- Helper functions used by RTL should be side-effect-light and synthesizer
  friendly.
- Use static casts instead of `$cast` in synthesizable code.

## FSM style

```systemverilog
typedef enum logic [1:0] {IDLE, BUSY, DONE} state_e;
state_e state_q, state_d;

always_ff @(posedge clk or negedge rst_n) begin
  if (!rst_n) state_q <= IDLE;
  else        state_q <= state_d;
end

always_comb begin
  state_d = IDLE;                  // top-of-block default = X-safe recovery
  unique case (state_q)            // NO `default` arm — see fsm-design SKILL
    IDLE: if (start_i) state_d = BUSY;
    BUSY: if (last_i)  state_d = DONE;
    DONE:              state_d = IDLE;
  endcase
end
```

Adding a `default:` arm to `unique case` disables the runtime existence
check in most simulators. Use the top-of-block default for recovery and
let `unique` do its job; if the simulator doesn't reliably fire the
check, fall back to plain `case` + `default:` instead. Full reasoning
in `hardware-fsm-design`.
