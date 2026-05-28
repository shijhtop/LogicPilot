---
name: hardware-rtl-audit
description: >-
  Run and interpret structural source audits for RTL risk patterns: sim/synth mismatch traps, non-synthesizable constructs, reset/FSM/CDC smells, delay controls, full_case/parallel_case, casex/casez, defparam, and VHDL after/wait-for. Use before lint/sim/synth or when reviewing an unfamiliar codebase for hidden RTL risks.
---

# RTL Source Audit

The `audit` stage is a fast, tool-independent source scan. It is not a
replacement for lint, CDC analysis, simulation, or synthesis; it catches
high-risk patterns early so the agent knows where to focus review.

Run it through the shipped driver:

```bash
python3 <flow>/logicpilot.py audit --config flow.toml
```

The result is JSON with `findings`, `summary`, `warnings`, and a compact `tail`.

## What the audit looks for

The rules are intentionally conservative and trace back to common
simulation/synthesis mismatch and FPGA optimization problems:

- `#delay`, `wait for`, VHDL `after` in RTL source.
- Verilog `full_case` / `parallel_case` synthesis pragmas.
- `casex` and reviewed `casez` use.
- `case` statements without a visible `default` / VHDL `others`.
- `defparam` and heavy macro-parameterization patterns that hurt reuse.
- `initial`, `$display`, `$finish`, `$random`, `force/release` in files listed
  as synthesizable RTL.
- SystemVerilog verification-only constructs in RTL globs: classes,
  randomization, covergroups, program blocks, mailboxes, semaphores, events,
  and DPI imports/exports.
- Blocking assignment in an edge-triggered Verilog block and nonblocking
  assignment in an `always_comb`/`always @*` block.
- Plain combinational `always @(...)` sensitivity lists that are not `@*`.
- Deprecated VHDL arithmetic packages such as `std_logic_arith`.

## Interpreting findings

- **high**: likely non-synthesizable or a known sim/synth mismatch trap. Review
  immediately before simulation results are trusted.
- **medium**: legal in some contexts but risky; confirm the intent and tool
  behavior.
- **low**: style/inference hint; usually not a blocker.

The audit can report false positives because it is a source heuristic, not a
parser. Treat it as a review queue, not a verdict.

## Workflow

1. Run `audit`.
2. For every high finding, decide: fix, move to testbench, or waive with a
   reason.
3. Run lint and simulation after fixes.
4. Run synthesis and compare the report to the intended hardware inference.
5. For multi-clock or reset issues, hand off to `hardware-cdc` and
   `hardware-reset-design`.

## Testbench audit

Use `tb-audit` for verification-environment risks such as waveform-only tests,
missing PASS markers, missing seed logging, coverage without checkers, `#0` race
workarounds, and unclear thread synchronization:

```bash
python3 <flow>/logicpilot.py tb-audit --config flow.toml
```

## Definition of done

No unexplained high findings remain; medium findings have a rationale or a fix;
the result is followed by lint/sim/synth rather than treated as sign-off.
