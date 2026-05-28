---
name: hardware-constraints
description: >-
  Author timing and pin constraints: clock definitions, generated/PLL clocks, I/O delays, and exceptions (false paths, multicycle, clock groups). Use for SDC/XDC/.pcf, create_clock, set_input_delay, false path, multicycle, clock groups, or when timing/Fmax looks wrong or unconstrained.
---

# Timing Constraints (SDC / XDC / PCF)

A timing report is only as meaningful as the constraints behind it. **No clock
constraint → no real Fmax**, and undeclared clock relationships make the static
timing analyzer either over-constrain (false failures) or under-constrain
(false passes on real CDC paths). Constraint authoring is a front-end activity:
write the constraints alongside the RTL, not after place-and-route.

The three formats in this plugin's flows are all SDC-family or pin files:

- **Quartus/open** `.sdc` and **Vivado** `.xdc` — Synopsys Design Constraints
  (SDC) Tcl commands. Same core commands; small vendor differences.
- **nextpnr/ice40** `.pcf` — *pin* constraints only (no timing); the clock
  frequency target is given separately (e.g. a frequency goal or a minimal SDC).

## The minimum every design needs

1. **Define every clock.** Without `create_clock` the tool has no period to
   check against. Map the project `clock_mhz` to a period:
   ```tcl
   create_clock -name clk -period 20.000 [get_ports clk]   ;# 50 MHz
   ```
2. **Constrain the I/O** if timing across the chip boundary matters:
   ```tcl
   set_input_delay  -clock clk 2.0 [get_ports data_in]
   set_output_delay -clock clk 3.0 [get_ports data_out]
   ```
3. **Tell the tool about multiple clocks.** If two clocks are asynchronous and
   exchange data through a synchronizer, declare them so STA does not try to
   close timing on the (correctly) asynchronous crossing.

## Generated, derived, and PLL clocks

- A clock produced on-chip (divided counter, gated, MUX-selected, PLL output)
  is a **generated clock**: `create_generated_clock` (Altera/open) ties it to
  its source so STA knows the relationship. For Altera PLLs, `derive_pll_clocks`
  generates the PLL output clock constraints automatically.
- **Prefer a clock enable over a gated or derived clock.** A clock enable adds
  no clock skew and burns no PLL, but a clock-enabled path runs every N cycles —
  so constrain it as a **multicycle path** (`set_multicycle_path -setup N`,
  `-hold N-1`). Gated/ripple clocks create skew, hold problems, and lower Fmax;
  only use them with a vendor clock-control primitive and proper constraints.

## Timing exceptions — tell the tool what NOT to check normally

- **`set_false_path`** — for genuinely asynchronous crossings (a 2-FF
  synchronizer's first stage, reset-synchronizer inputs, static config bits that
  never change in operation). Don't false-path a real synchronous path to "make
  timing" — that hides a bug.
- **`set_clock_groups -asynchronous`** — the cleaner way to say "these clock
  domains are mutually asynchronous"; covers all paths between them at once
  instead of many `set_false_path`s.
- **`set_multicycle_path`** — for paths that legitimately have more than one
  clock period to settle (clock-enabled logic, slow data on a fast clock). Set
  the hold multicycle one less than the setup multicycle.
- **`set_max_delay`/`set_min_delay`** — bound a CDC data path's skew when you
  must keep both ends within a window (e.g. multi-bit data captured by a
  synchronized enable), instead of a blanket false path.

## Workflow

1. Identify clocks (primary + generated) and their frequencies; write
   `create_clock`/`create_generated_clock`.
2. Constrain I/O against the relevant clock if board timing matters.
3. List clock-domain crossings (use `hardware-cdc`) and declare them:
   `set_clock_groups -asynchronous` for async domains; `set_false_path` /
   `set_max_delay` on the specific synchronizer/data paths.
4. Add `set_multicycle_path` for clock-enabled or genuinely slow paths.
5. Re-run `synth`/`pnr` and read the timing report — now the numbers mean
   something. Negative slack with correct constraints is a real timing problem
   (hand off to `fpga-timing-closure`); negative slack from missing/​wrong
   constraints is a constraint bug.

## Definition of done

Every clock defined; every async crossing declared (false path / clock groups /
bounded); I/O constrained where it matters; clock-enabled paths given multicycle
exceptions. The timing report is now trustworthy. See
`references/sdc-cookbook.md` for the command patterns and
`references/sdc-templates.md` for pasteable per-vendor snippets
(open / Xilinx / Intel).

## Reset, CDC, and synchronizer constraints

Constraints must match the CDC/reset architecture, not silence warnings
globally:

- Define every real clock and generated clock before interpreting timing.
- For unrelated clocks, declare the relationship (`set_clock_groups
  -asynchronous` or equivalent) and then constrain the synchronizer/FIFO paths
  deliberately according to vendor guidance.
- For a 2FF synchronizer, false-path the asynchronous path to the first stage
  where appropriate, but do not hide ordinary synchronous timing after the
  synchronizer.
- For reset synchronizers, raw async reset assertion is usually treated as an
  asynchronous/false path, while reset release must still be reviewed for
  recovery/removal or equivalent timing.
- Multicycle paths must include both setup and hold adjustments; a setup-only
  multicycle exception is a common sign-off bug.

Never add broad false paths to make timing green. Every exception needs a named
architectural reason and a matching RTL pattern.
