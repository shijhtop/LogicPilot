# Verilog / SystemVerilog — synthesizable subset

The synthesizable subset is the part accepted by the configured synthesis tool.
The portable core below is the default LogicPilot review standard.

## Intent-revealing SystemVerilog

| construct | use for | review rule |
|---|---|---|
| `logic` | single-driver variables | does not imply a flop by itself |
| `always_ff` | clocked sequential logic | one clock, optional reset, nonblocking assignments |
| `always_comb` | combinational logic | blocking assignments and complete defaults |
| `always_latch` | intentional latch | rare; document and verify target acceptance |
| `typedef enum logic [N-1:0]` | FSM states/opcodes | avoid default `int` enum base in RTL |
| packed `struct` | protocol/data bundles | verify bit ordering and width |
| `interface` + `modport` | repeated signal bundles | keep directions clear; verify synthesis support |
| `package` | shared types/constants/functions | compile before users |

## Data types and dimensions

- Packed dimensions are bits; unpacked dimensions are arrays/memories.
- Use sized literals or SV fill literals (`'0`, `'1`) deliberately.
- Declare signedness explicitly when arithmetic matters.
- Cast when width or signedness changes are intentional.
- Prefer `typedef` names that encode meaning, not just width.
- Prefer 4-state `logic` for hardware state; use 2-state `bit`/`byte` only when
  masking X/Z behavior is intentional.
- Use static casts for RTL; keep `$cast` in TB/reference models.

## Assignment rules

- Sequential logic uses nonblocking `<=`.
- Combinational logic uses blocking `=`.
- Do not mix assignment types in one procedural block.
- **Two `always` blocks assigning the same variable (even both using `<=`)
  is a race condition, not a wired-OR.** Synthesis warns `multiple-driver
  net with unknown wired-logic type`; sim result depends on scheduler order.
  One driver per variable, always.
- Do not use `#0` to repair scheduling. `#0` schedules into the inactive-
  events region of the same time-step (not the nonblocking-update region),
  so it cannot guarantee ordering against `<=` updates from other blocks.
- **Never hand-write `always @(a or b)` for combinational logic** —
  missing signals or temp-read-before-write cause pre / post-synth
  divergence. Use `always @*` (Verilog-2001) or `always_comb` (SV) so the
  sensitivity list is implicit and complete.

## Case and branch rules

- Every combinational `case` has a reviewed `default`.
- Use `unique` / `priority` only when the design intent is actually unique or
  priority-ordered and is verified.
- Avoid `casex` in RTL. Use `casez` only for intentional mask bits.
- Do not use `full_case` or `parallel_case` pragmas to hide incomplete decode.
- **`case (1'b1)` against boolean case-items** implies priority semantics
  in simulation (first matching arm wins); synthesis may collapse it to a
  parallel mux when items are mutually exclusive (one-hot). Reserve for
  one-hot FSM next-state; otherwise prefer `if / else if` to make priority
  explicit.

## Packages, `$unit`, and file order

Use packages for shared declarations:

```systemverilog
package types_pkg;
  parameter int unsigned DATA_W = 32;
  typedef enum logic [1:0] {IDLE, BUSY, DONE} state_e;
endpackage
```

Then list packages before users in `flow.toml` with `src_ordered` when glob order
is not reliable. Avoid shared declarations in `$unit`; they depend on source
order and separate-compilation behavior.

Also keep a visible language-context policy:

```systemverilog
`default_nettype none
timeunit 1ns;
timeprecision 1ps;
```

A project may enforce this centrally, but the policy must be explicit.

## Interfaces

Interfaces reduce port-list mistakes, but they also hide structure if abused.

- Define `modport`s for each role.
- Keep synthesizable interface contents simple.
- Use clocking blocks for testbench drive/sample timing, not for RTL logic.
- Use virtual interfaces in class-based TB components.

## Testbench-only SV features

Keep these out of synthesizable RTL files:

```text
class, randomize, rand/randc, dynamic array, queue, associative array,
string/chandle, mailbox, semaphore, event, fork/join testbench threads,
covergroup, program block, DPI import/export, clocking block in RTL interface,
$display/$finish/$urandom in design logic
```

Some assertions can be bound to RTL for simulation/formal, but they should not
change the synthesized hardware behavior.

## Tool reality check

A construct can be legal SystemVerilog and still unsupported by a specific
synthesizer. Run audit, lint, simulation, and synthesis early when using
interfaces, packages, structs, enums, or generate-heavy code.
