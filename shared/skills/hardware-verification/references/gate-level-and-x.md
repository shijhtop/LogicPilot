# Gate-level simulation, equivalence, and X handling

Use this reference when RTL simulation passes but a synthesized/post-route netlist
does not, or when deciding whether gate-level simulation (GLS) is worth running.

## What GLS is for

GLS is not a replacement for RTL verification. It is a targeted check for issues
that only appear after synthesis/implementation:

- wrong or missing reset/initialization assumptions;
- X optimism in RTL `if/case` that hides unknowns until the gate netlist;
- unintended latch, multi-driver, or inferred tri-state behavior;
- clock-gating, generated-clock, or enable logic mistakes;
- vendor primitive/cell-model mismatches;
- post-route SDF/timing checks when the sign-off flow requires them.

Run the same self-checking testbench where possible. The testbench still needs a
clear PASS/FAIL marker; a waveform-only GLS run is not a regression.

## X optimism / X pessimism checklist

- Do not use `casex` in synthesizable RTL; prefer `unique casez` only when the
  don't-care bits are intentional and reviewed.
- Give every combinational output a default assignment before `case/if`.
- Reset all architecturally visible state that software or downstream logic can
  observe immediately after reset.
- Treat `X` in a scoreboard as a failure unless the spec explicitly allows an
  unknown/don't-care at that time.
- In SystemVerilog assertions, use `$isunknown()` on control signals, FSM state,
  valid/ready, enables, and mux selects.

## Equivalence checking

LEC/formal equivalence should prove that RTL and the optimized netlist implement
the same logic. It is usually cheaper and stronger than trying to hit every path
with GLS. Use GLS for initialization/timing/model issues; use LEC for
optimization correctness.

## Practical debug order

1. Confirm the RTL test still passes with the same seed and config.
2. Check synthesis warnings: latches, multiple drivers, width truncation,
   undriven nets, black boxes.
3. Run LEC. If it fails, debug the synthesis/constraint/black-box boundary before
   looking at waveforms.
4. If LEC passes but GLS fails, inspect reset/init, X propagation, cell models,
   and SDF/timing checks.
5. Reduce to the first divergence cycle and compare RTL vs gate waveforms at
   control boundaries before drilling into individual cells.
