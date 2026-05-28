---
name: hardware-rtl-design
description: >-
  Write synthesizable RTL/HDL (Verilog, SystemVerilog, or VHDL) for hardware targets. Use to create, scaffold, refactor, or review modules, FSMs, pipelines, AXI/Avalon interfaces, CDC logic, or testbench stubs, before writing any .v/.sv/.vhd/.vhdl, so code is synthesis-clean and lints cleanly, not just sim-correct.
---

# Hardware RTL Design

Goal: produce RTL that is **synthesizable, lint-clean, and timing-friendly**,
not merely simulatable. Code that simulates but infers latches, has width
mismatches, or crosses clock domains unsafely will pass `sim` and fail
`synth`/`pnr` later — fix it at the source here.

## Workflow

1. **Confirm the HDL language first.** Check `flow.toml` `[project] hdl`
   (or run `logicpilot.py --list`, which reports the auto-detected family).
   Verilog/SystemVerilog and VHDL have different toolchains and different
   synthesizable idioms — don't write a `.v` file for a VHDL project or vice
   versa. For a `mixed` project, confirm which language each new module should
   be in. The synthesizable rules below are written for Verilog/SV; the VHDL
   equivalents are noted at the end.
2. Clarify the spec: clock(s) and reset style (sync/async, active level),
   target family (from `flow.toml` `[toolchain]`), interfaces, throughput.
3. Write RTL following the rules below. For SystemVerilog packages/types/interfaces, resets, FSMs, CDC, or timing/area work, explicitly hand off to the specialized skills listed in the next section.
4. Run the source audit before lint on unfamiliar or non-trivial RTL:
   ```
   python3 <flow>/logicpilot.py audit --config flow.toml
   ```
   Treat high findings as review blockers unless there is a documented waiver.
5. Run the linter through the driver — do not hand-wave it:
   ```
   python3 <flow>/logicpilot.py lint --config flow.toml
   ```
   Read the JSON `status`, `tool`, and `tail`. Fix every width/latch/sensitivity
   warning before moving on.
6. Hand off to the `hardware-simulation` skill to prove behavior.

`<flow>` is the path to the shipped `logicpilot.py` (the install step symlinks
the project's `flow.toml`; if unsure, run `logicpilot.py --list` first).


## Specialized handoffs

Use these before writing or changing code in the corresponding area:

- SystemVerilog packages/types/interfaces/model boundaries → `systemverilog-design-modeling`.
- Reset architecture / RDC → `hardware-reset-design`.
- FSM/control sequencing → `hardware-fsm-design`.
- Code-level speed/area/resource optimization → `fpga-architecture-optimization`.
- Existing-code source-risk review → `hardware-rtl-audit`.
- Multi-clock / multi-reset crossings → `hardware-cdc`.
- Interface protocols and backpressure → `hardware-interfaces`.

Do not collapse these into generic style comments: each one changes real
hardware structure, constraints, or verification obligations.

## Synthesizable RTL rules

When writing `.sv`, prefer SystemVerilog features that reveal hardware intent: `logic`, typed parameters, packages for shared types, `typedef enum` for FSMs, packed structs for buses, `interface`/`modport` for repeated protocol bundles, and `always_ff`/`always_comb` for procedural intent. Keep classes, randomization, covergroups, DPI, mailboxes, and semaphores out of RTL source globs.

- One clock domain per `always_ff`/`always @(posedge clk)` block; never mix
  edges or clocks in one block.
- Sequential logic: non-blocking `<=`. Combinational logic: blocking `=` in
  `always_comb` / `always @(*)`. Never mix in one block.
- Fully specify combinational outputs (assign a default first) to avoid
  inferred latches. Every `case` gets a reviewed `default`/`others`. Do not use
  `full_case`/`parallel_case` to hide an incomplete decode; use `unique` or
  `priority` only to document a true intent and keep assertions/defaults.
- Match bit widths explicitly; size literals (`8'd0`, not `0`). Avoid implicit
  truncation.
- Reset only what needs it. Async reset must be on the sensitivity list and
  released synchronously (reset synchronizer) to avoid recovery/removal issues.
- No `#delay` in synthesizable code. No `initial` for hardware state except
  target-supported FPGA initialization/ROM preload with an explicit comment; use
  reset or a scrub sequence for portable RTL.
- Register module boundaries for timing; keep deep combinational paths short.

## Clock domain crossing (CDC)

- Single-bit control: 2-flop synchronizer. Multi-bit: gray-code (counters) or
  async FIFO / handshake. Never let a multi-bit bus cross unsynchronized.
- Mark CDC paths so timing tools can ignore/constrain them (set_false_path /
  set_max_delay in the .xdc/.sdc).

## Output

Place RTL under `rtl/` matching the `src` globs in `flow.toml`. Name the top
module to match `[project] top`. After writing, ALWAYS run the `lint` stage and
report the result before claiming the design is done.

## VHDL equivalents

For VHDL projects the same intent applies with different syntax:
- Clocked process: `process(clk) ... if rising_edge(clk)`; async reset adds
  `rst` to the sensitivity list and an `if rst = '1'` branch released
  synchronously.
- Use `signal` for hardware nets; `variable` only with understood
  immediate-update semantics. Drive each signal from one process.
- Fully assign combinational outputs on all branches (default assignment) to
  avoid latches; every `case` needs `when others`.
- Use `numeric_std` (`unsigned`/`signed`), not the non-standard `std_logic_arith`.
- No `wait`/`after` timing in synthesizable code (testbench-only).

## Reference

See `references/style-checklist.md` for a pre-commit checklist and common
synth-vs-sim mismatch traps.
