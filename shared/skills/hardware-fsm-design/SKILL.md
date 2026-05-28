---
name: hardware-fsm-design
description: >-
  Design and review finite-state machines in Verilog/SystemVerilog/VHDL: one-/two-/three-process styles, state encoding (one-hot/binary/gray), safe default assignments, registered outputs, and full_case/parallel_case/unique/priority pitfalls. Use when writing or reviewing state machines, control logic, arbiters, or code with enum/case/state.
---

# FSM Design & Review

A state machine is the control contract of the block. It must be easy to read,
easy to verify, and unambiguous to synthesis.

## Preferred SystemVerilog style (two-process)

```systemverilog
typedef enum logic [1:0] {IDLE, BUSY, DONE} state_e;
state_e state_q, state_d;

always_ff @(posedge clk or negedge rst_n)
  if (!rst_n) state_q <= IDLE;
  else        state_q <= state_d;

always_comb begin
  state_d = IDLE;               // top-of-block default = X-safe recovery
  ready_o = 1'b0;
  done_o  = 1'b0;
  unique case (state_q)         // NO `default` arm — see rule below
    IDLE: begin ready_o = 1'b1; if (start_i) state_d = BUSY; end
    BUSY: begin                  if (last_i)  state_d = DONE; end
    DONE: begin done_o  = 1'b1;               state_d = IDLE; end
  endcase
end
```

Three-process variant (registered outputs) when outputs feed timing-critical
paths, external interfaces, or CDC boundaries. See
`references/fsm-coding-patterns.md`.

## Hard rules

- **Enum base must be explicit packed 4-state:** `typedef enum logic [N-1:0]
  {…}`. Default base is 32-bit 2-state — masks X / reset behavior. Use
  `enum` (not `parameter` or `` `define ``) so waveforms display symbolic
  state names and the tool catches illegal cross-type assignments.
- **Defaults at the top of the comb block** before the `case`. No latches.
- **No `full_case` / `parallel_case` / `casex`** in synthesizable FSMs.
- **`unique case` / `priority case`** without a `default` arm:
  - `priority case` = asserts at least one item matches (safe `full_case`).
  - `unique case` = asserts exactly one item matches AND all enumerated
    (safe `full_case + parallel_case`).
  - Adding a `default` arm **disables the runtime check** in most
    simulators. If you need a fallback, drop the modifier and rely on
    the top-of-block default assignment instead.
  - **Simulator caveat**: behavior varies — confirm with your simulator
    that the runtime check actually fires before relying on it. If it
    doesn't, fall back to plain `case` + a reviewed `default:` arm.
  - **When NOT to use** `unique` / `priority`: if the comb-block default
    assignment already covers every unlisted input (typical latch-free
    decoder/mux), `unique case` will fire a runtime error on benign
    inputs (e.g. `enable=0`). Stick with the plain `case` + default style.
- **Comb-block default policy** — three choices:
  - `state_d = IDLE` (default): X-safe; recoverable from glitches; required
    by scan / formal-equivalence / safety-critical flows.
  - `state_d = state_q` (hold): PLD-era style; hides uncovered transitions.
  - `state_d = 'x`: pre-synth sim shows uncovered paths as X; synth treats
    as don't-care; useful for debug + Fmax but unsafe in deployment.
- One output is driven by one block. No mixing blocking / nonblocking in one
  block.

## Encoding decisions

- **Binary** — fewer FFs; ASIC or many-state.
- **One-hot** — simpler decode; often best on FPGA LUT fabric / high-Fmax.
- **Gray** — only for sequences crossing clock domains or single-bit-step
  pointers. Not a generic speed trick.

Let the synthesis tool pick unless you have evidence. If forced, document the
reason and check the synthesis report for the actual encoding.

## Verification hooks

```systemverilog
assert property (@(posedge clk) disable iff (!rst_n) !$isunknown(state_q));
assert property (@(posedge clk) disable iff (!rst_n) state_q inside {IDLE, BUSY, DONE});
```

For one-hot, assert `$onehot(state_vector)`. Cover every reachable state and
key transition.

## Review checklist

- Reset state defined and legal.
- `state_d` defaulted before the `case`; all outputs assigned on all paths.
- Every state has a documented transition condition.
- Illegal/default behavior is intentional.
- Outputs registered if they leave the block or matter for timing/glitches.
- No `full_case` / `parallel_case` / `casex`.
- Assertions/coverage cover legal states and key transitions.

## Definition of done

FSM style is explicit, latches are structurally impossible, encoding is chosen
or delegated with rationale, illegal-state behavior is defined, and
testbench/assertions cover every state and critical transition.
