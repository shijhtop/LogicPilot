---
name: systemverilog-design-modeling
description: >-
  SystemVerilog design/modeling specialist. Use when writing or reviewing .sv RTL, packages, typedefs, enums, packed structs/unions, arrays, interfaces, modports, generate blocks, always_ff/always_comb/always_latch, or behavioral/transaction-level models.
---

# SystemVerilog Design & Modeling

Use SystemVerilog to make hardware intent explicit: typed declarations, clear
namespaces, intent-specific processes, reusable interfaces, and a visible
boundary between RTL, behavioral models, and transaction-level models.

## Workflow

1. **Classify every file.**
   Decide whether it is RTL, package, interface, testbench, behavioral reference
   model, or transaction-level model. Keep implementation RTL out of TB/model
   globs, and keep dynamic verification constructs out of RTL globs.

2. **Control declarations and compile order.**
   Put shared `typedef`, enum, struct, parameters, constants, and helper
   functions in named packages. Compile packages before users with
   `src_ordered` when glob order is not sufficient. Avoid declarations in
   `$unit`; they create source-order and separate-compilation hazards.

3. **Set language context deliberately.**
   Use ``default_nettype none`` in Verilog/SV source policy, and use
   `timeunit/timeprecision` or a controlled ``timescale`` policy so simulation
   time does not depend on compile context.

4. **Use hardware-accurate types.**
   Prefer 4-state `logic` for hardware registers/signals. Use 2-state types only
   when masking X/Z behavior is intentional. For FSMs and opcodes, use
   `typedef enum logic [N-1:0]` with explicit encoding when debug, assertions, or
   implementation equivalence need stable values.

5. **Bundle data without hiding width.**
   Use packed structs for protocol/data bundles, packed arrays for bit layout,
   and unpacked arrays for memories/collections. Use `$bits` and static casts
   where widths matter. Avoid dynamic arrays, queues, strings, mailboxes,
   semaphores, and DPI in synthesizable RTL.

6. **Use intent-specific processes.**
   Use `always_ff` for sequential logic, `always_comb` for pure combinational
   logic, and `always_latch` only when the latch is intentional. Keep assignment
   discipline: nonblocking in sequential blocks, blocking in combinational
   blocks.

7. **Model FSMs explicitly.**
   Separate state register and next-state/output logic. Give safe defaults,
   illegal-state handling, and reviewed `unique`/`priority` use. Do not rely on
   default enum `int` width/base for implementation state.

8. **Use hierarchy and interfaces deliberately.**
   Prefer named parameter overrides and named port connections. Use interfaces to
   group repeated protocol signals, but define `modport`s for each role. Keep
   synthesizable interface methods simple and `automatic`; reserve clocking
   blocks and virtual interfaces for the testbench.

9. **Keep high-level models in their lane.**
   Behavioral and transaction-level models can use tasks, functions, objects,
   delays, dynamic containers, and abstract method calls, but they are specs or
   verification models until refined into clocks, storage, handshakes, and RTL.

## Quick review checks

- Packages exist for shared types/constants; no accidental `$unit` declarations.
- File order compiles packages/interfaces before modules that import/use them.
- `default_nettype none` and timebase policy are visible or project-enforced.
- Enum bases are explicit; FSM encoding and illegal-state behavior are reviewed.
- Packed vs unpacked dimensions match hardware intent.
- Static casts are used for intentional width/signedness changes; `$cast` stays
  out of RTL.
- No class/randomization/coverage/DPI/dynamic container constructs in RTL globs.
- Interfaces have `modport`s; TB timing uses clocking blocks, not RTL logic.
- `always_ff`/`always_comb`/`always_latch` contents match the block intent.

## References inside this skill

- `references/sv-packages-types.md`
- `references/sv-procedural-fsm.md`
- `references/sv-interfaces-hierarchy-tlm.md`
- `references/sv-model-boundaries.md`
- `references/sv-rtl-modeling.md`

## Definition of done

The SystemVerilog model has clear namespace ownership, type-safe hardware
intent, verified compile order, no misplaced verification-only constructs, and
passes LogicPilot source audit, lint, simulation, and synthesis for the selected
flow.
