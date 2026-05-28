---
name: fpga-timing-closure
description: >-
  Close timing and optimize area/resource usage for an FPGA design. Use for timing, Fmax, slack, WNS/TNS, critical path, place-and-route, congestion, or reducing LUT/FF/BRAM/DSP usage, especially when a pnr/synth run reports negative slack or over-budget utilization.
---

# Timing Closure & Area Optimization

Make the design meet its clock and fit its device. This is **report-driven
iteration**: a synth / pnr run has already produced WNS / TNS / utilization
numbers, and you're closing the loop by changing RTL or constraints,
re-running, comparing. For **RTL-stage** authoring (designing for timing
*before* the first synth run), see `fpga-architecture-optimization`.

## Workflow

1. Run place-and-route (or implementation) to get real timing:
   ```
   python3 <flow>/logicpilot.py pnr --config flow.toml
   ```
2. Read the JSON `metrics`:
   - `fmax_mhz` vs the `clock_mhz` target.
   - `wns_ns` — negative means timing is NOT met. The driver also raises a
     `warnings` entry for negative WNS even when the tool exits 0.
   - `luts/ffs/bram/dsp` for area.
3. Diagnose the critical path from `build/logs/pnr.log` (or the vendor timing
   report). Identify whether it's logic-depth, fanout, routing, or a bad
   constraint.
4. Apply ONE class of fix at a time, re-run, compare. Tracking one change per
   iteration is what makes the metric movement interpretable.

## Timing fixes (highest leverage first)

- **Pipeline the critical path**: insert register stages to cut combinational
  depth. Biggest, most reliable Fmax win; costs latency + FFs.
- **Retiming**: let the tool move registers across logic (`abc` in yosys,
  `-retiming`/phys_opt in Vivado).
- **Reduce fanout**: duplicate high-fanout registers/drivers.
- **Fix the constraint, not the design**: an over-tight or missing clock
  constraint produces phantom violations. Verify the .pcf/.xdc/.sdc clock
  period matches `clock_mhz`. Add false/multicycle paths for CDC and
  genuinely-relaxed paths.
- **Balance logic**: rebalance unbalanced mux/adder trees; use DSP/BRAM
  primitives instead of LUT-built equivalents.

## Area fixes

- Share resources: time-multiplex expensive units (one multiplier, scheduled).
- Map memory to BRAM instead of distributed LUT-RAM (or vice-versa if BRAM is
  the scarce resource).
- Remove dead/duplicate logic; check for unintended replication from `keep`
  attributes.
- Narrow datapaths to the bits actually needed.

## Trade-offs

Area and speed trade against each other and against latency. State the
trade-off you're making to the user (e.g. "+3 FFs and +1 cycle latency to gain
~40 MHz"). Don't silently change the design's latency contract.

## Definition of done

`wns_ns >= 0` (timing met) at the target clock AND utilization within budget.
Report final Fmax, WNS, and utilization. The optimized netlist still needs
gate-level functional verification (GLS / LEC), but that is a back-end
stage and out of scope here.

## Code-level optimization handoff

When the critical path points to RTL structure rather than a bad constraint,
hand off to `fpga-architecture-optimization` before editing code. The common
code-level fixes are:

- pipeline the path and align valid/control signals;
- balance adder/mux/reduction trees;
- remove accidental priority chains;
- duplicate/register high-fanout enables and state decodes;
- change memory/DSP coding style so BRAM/DSP/SRL inference matches intent;
- state the latency/resource trade-off before applying it.

After the RTL change, rerun sim before trusting the improved timing report.
