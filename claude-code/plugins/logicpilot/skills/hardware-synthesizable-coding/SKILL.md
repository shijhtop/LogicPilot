---
name: hardware-synthesizable-coding
description: >-
  Reference for what is and isn't synthesizable in Verilog, SystemVerilog, and VHDL, and the idioms that infer intended hardware (flip-flops, latches, muxes, memories, FSMs, arithmetic). Consult when writing or reviewing RTL or debugging a sim-vs-synth mismatch, inferred latch, or blocking-vs-nonblocking choice. Knowledge base for hardware-rtl-design.
---

# Synthesizable HDL Coding Knowledge

The synthesizable subset is the part of the language that maps to real gates and
registers. Code outside it may simulate but won't synthesize, or will synthesize
to something other than what the simulation showed. The goal of every idiom
below is that **what you simulate is what you get in silicon.**

This knowledge is target-agnostic: the synthesizable subset and inference
patterns apply to BOTH FPGA and ASIC. See `## ASIC vs FPGA RTL differences`
below for the handful of habits ASIC adds.

## ASIC vs FPGA RTL differences

The synthesizable subset is the same; a few RTL habits differ:

- **Reset every state element you depend on.** ASIC FFs have no defined
  power-up value without an explicit reset; do not rely on `initial` or
  `don't care` reduction. (FPGA can use vendor-documented power-up init
  for some primitives.)
- **No FPGA primitives.** No inferred BRAM / DSP / SRL / LUTRAM. Memories
  come from compiled macros, register files, or instantiated SRAM
  macros.
- **No hand-built gated clocks.** Use clock enables and let synthesis
  insert ICG (integrated clock gating) cells; gated clocks built by hand
  in RTL fight CTS and DFT.
- **DFT-friendly from the start.** Scan-friendly resets (async-assert /
  sync-release per domain, no `initial`), no latches, testable clocking
  (scan-mode bypass for internally-generated clocks), no combinational
  feedback. These are RTL decisions; scan insertion / ATPG / MBIST live
  in the back-end flow which is out of scope.

## The mental model

When you read RTL, see hardware, not statements. `always @(posedge clk) q <= d;`
is a flip-flop. A combinational block that doesn't assign an output on every path
is a latch. An `if/else` is a mux. An `+` is an adder; a `*` is a multiplier (or
a DSP block). Write the code that describes the structure you want.

## The rules that prevent 90%+ of bugs

These are language-independent in intent (syntax differs by language):

1. **Separate sequential and combinational logic.** Clocked process/block holds
   state; combinational block computes next values. The two-always-block FSM
   (clocked state register + combinational next-state/output) is the most
   robust, debuggable style.
2. **Assignment discipline (Verilog/SV):** nonblocking `<=` in clocked blocks,
   blocking `=` in combinational blocks. Never mix them in one block. This is
   the single most important rule for matching sim to synthesis.
3. **Fully specify combinational outputs.** Assign a default at the top of the
   block, give every `case` a `default`/`when others`. A missing branch infers a
   latch — almost always a bug.
4. **One driver per signal**, one clock + one reset per sequential block, no
   mixed clock edges in a block.
5. **Size everything.** Explicit widths and sized literals; no reliance on
   implicit truncation/extension.
6. **No simulation-only constructs in RTL:** `#delay`, most `initial` (FPGA
   power-up init is family-specific), 4-state `===`/`!==`, `wait`/`after`
   (VHDL). These are testbench tools.

## What infers what

See `references/inference-patterns.md` for the canonical code shapes that infer
each primitive: edge-triggered FF, sync vs async reset, latch (and how to avoid
it), mux/priority-mux, one-hot vs binary FSM, RAM/ROM (and how to hit BRAM vs
distributed RAM), shift register, counter, and arithmetic → DSP mapping.

## Language specifics

- Verilog / SystemVerilog → `references/verilog-sv.md` and `systemverilog-design-modeling` (packages,
  typedefs, packed vs unpacked dimensions, enums, structs/unions, interfaces,
  modports, `logic` vs `reg/wire`, always_ff/comb/latch, and the SV
  synthesizable subset that tools actually support).
- VHDL → `references/vhdl.md` (process sensitivity, signal vs variable,
  numeric_std, rising_edge, record/array types, std_logic resolution, the
  synthesizable subset and `--std` selection).
- Language standards / editions → `references/standards.md` (which IEEE standard
  and revision to cite: SystemVerilog 1800-2023, VHDL 1076-2019, UVM 1800.2,
  PSL, UPF — and why the synthesizable subset is tool-defined in practice).

## How to use this in review

When reviewing or writing RTL, check against `references/inference-patterns.md`
and the language file, then run the `lint` stage (via hardware-rtl-design). Flag any
construct that simulates but won't synthesize, and any block that could infer an
unintended latch, multiplier, or memory. State the inferred hardware explicitly
when you explain a fix ("this missing else infers a latch on `y`").

## RTL methodology source-derived non-negotiables

Use these as a quick review lens whenever a simulation result and synthesized
hardware might diverge:

1. **Clocked blocks use nonblocking assignments; combinational blocks use
   blocking assignments.** Do not mix assignment types in one procedural block.
2. **Delay controls are modeling constructs, not RTL timing.** `#delay`,
   `assign #`, VHDL `after`, and `wait for` belong in testbenches or behavioral
   models, not synthesizable RTL.
3. **`full_case` and `parallel_case` are not optimization magic.** They can
   remove logic that simulation still appears to use. Fix the decode with
   defaults, complete assignments, and assertions instead.
4. **Avoid `casex`; review every `casez`.** X/Z wildcards can hide an unknown or
   floating signal exactly when the simulator should be warning you.
5. **Parameterize with `parameter`/`localparam` and typed SV parameters.** Avoid
   cross-hierarchy `defparam`; it is fragile and hard to audit.
6. **Intent-revealing SV constructs help tools help you.** Prefer `always_ff`,
   `always_comb`, `typedef enum`, `logic`, packages, packed structs for buses,
   interfaces/modports for repeated protocol bundles, and explicit named port
   connections in new SystemVerilog RTL.
7. **Verification features stay in the verification tree.** Classes,
   randomization, queues, covergroups, mailboxes, semaphores, events, program
   blocks, and DPI belong in TB/model files, not in synthesizable RTL globs.
8. **Never hide initialization behind `synopsys translate_off`.** `initial`
   blocks, `force` / `release`, set / reset helpers wrapped in
   `translate_off` boot in pre-synthesis sim but do not exist post-synthesis
   — guaranteed sim / synth mismatch.

See `references/rtl-coding-rules.md` for the expanded checklist.
