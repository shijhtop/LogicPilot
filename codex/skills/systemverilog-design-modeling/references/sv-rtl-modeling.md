# SystemVerilog RTL modeling checklist

## Declarations

- Shared types/constants live in packages, not `$unit`.
- Packages and interfaces compile before users.
- `default_nettype none` is visible or project-enforced.
- `timeunit/timeprecision` or a controlled ``timescale`` policy is visible.

## Types

- Prefer 4-state `logic` for hardware signals and registers.
- Use 2-state types only with an explicit reason.
- Use `typedef enum logic [N-1:0]` for FSM states/opcodes.
- Use packed structs for bit-exact bundles.
- Use unpacked arrays for memories.
- Use `$bits` and static casts when width matters.
- Avoid `$cast`, dynamic arrays, queues, strings, DPI, classes, randomization,
  coverage constructs, mailboxes, and semaphores in RTL source files.

## Procedural blocks

- `always_ff`: one clock + optional reset; only `<=`; tool enforces
  single-driver check on LHS.
- `always_comb`: only `=`; tool auto-builds the complete sensitivity list
  and **flags accidental latches** (any branch that doesn't assign every
  output); no `#delay` / `@event` / `wait` allowed.
- `always_latch`: only when a latch is the design intent; do **not** write a
  top-of-block default or the latch won't be inferred.

## Port style

- ANSI port header — direction + type + width in one declaration:
  `module m (output logic [7:0] q, input logic [7:0] d, input clk);`
  Never use the legacy Verilog-95 split-declaration style.
- Instantiate with `.name` / `.*` implicit ports — the tool checks name
  and width match at elaboration time. Fall back to explicit `.port(net)`
  only when names differ or width must be sliced. **Never positional**
  (order errors pass silently in sim).

## Control

- Prefer enum FSMs with explicit base/width.
- Use `unique`/`priority` only as true intent.
- Keep `default` for recovery or reviewed illegal-state handling.
- Avoid `casex`; review every `casez`.

## Interfaces and hierarchy

- Interfaces should define `modport`s.
- Clocking blocks and virtual interfaces are TB constructs.
- Use named parameter overrides and named port connections.
- Use `src_ordered` for dependency-sensitive packages/interfaces.
