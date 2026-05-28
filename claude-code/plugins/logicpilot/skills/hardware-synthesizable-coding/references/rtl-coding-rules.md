# RTL coding rules distilled for agent use

This file condenses RTL methodology into actionable checks. Use it as a coding/review checklist.

## Blocking vs nonblocking

- Use `<=` for sequential logic updated on a clock edge.
- Use `=` for combinational logic in `always_comb` / `always @*`.
- Do not read and write the same variable with mixed assignment types in one
  simulation region.
- **Testbench drives DUT inputs with nonblocking `<=` to avoid 0-delay
  races with `@(posedge clk)` sampling**. Use `@(posedge clk); #1;` (or an
  SV clocking block) before applying stimulus so the change lands strictly
  after the DUT's sampling edge.
- **When a single `always @(posedge clk)` block contains both combinational
  temporaries and registered outputs, use `<=` for every assignment** —
  do not promote the temporaries to `=`.

## Delay controls

- **Never use `#0` to repair scheduling.** `#0` only re-queues the
  assignment into the *inactive events* region of the **same** time-step;
  it does not order it after nonblocking LHS updates and frequently masks
  the real race rather than fixing it.
- **Intra-assignment delay on a nonblocking** (`x <= #N expr;`) is the only
  RHS form that models transport-style delay correctly in behavioral / TB
  models.
- **LHS procedural delay** (`#N x = expr;` or `#N x <= expr;`) does **not**
  model any real hardware — it lets later input changes propagate in less
  than `N` units and silently drops events that arrive during the delay
  window.
- RTL timing comes from registers, clock constraints, and STA; express a
  delay with a counter, pipeline, or clock enable when hardware behavior
  requires it.

## `full_case` / `parallel_case`

- Never add these pragmas to suppress a latch warning.
- A missing branch in simulation should remain visible; do not tell synthesis
  it cannot happen unless the design has assertions proving the invariant.
- **`full_case` does NOT eliminate latches inferred from incomplete output
  assignment.** It only suppresses the latch inferred from a *missing case
  item*. If the case items themselves do not assign every output on every
  branch, latches are still inferred — fix with defaults at the top of the
  block.
- Use `unique case` / `priority case` only when the semantic intent is true
  AND the tool's runtime checks reliably fire. Adding a `default:` arm to
  `unique case` disables the runtime existence check in most simulators
  (defeating the point) — prefer top-of-block default assignment for
  X-safe recovery. If the simulator does not honor the runtime check,
  fall back to plain `case` + a reviewed `default:` arm. See
  `hardware-fsm-design` for FSM-specific guidance.

## Parameters and ports

- Prefer instance parameter overrides: `#(.WIDTH(W))`.
- Use `localparam` for derived constants that must not be overridden.
- Avoid `defparam`; it creates fragile hierarchy-dependent behavior.
- Prefer explicit named port connections for safety. `.*`/`.name` can be useful
  in highly controlled top-level code, but audit renamed or width-changed ports.

## X and 2-state/4-state

- RTL design types should generally be 4-state in simulation so X bugs are
  visible.
- 2-state types can improve verification performance but can also mask X
  initialization/propagation issues; use intentionally, not as a default escape.
