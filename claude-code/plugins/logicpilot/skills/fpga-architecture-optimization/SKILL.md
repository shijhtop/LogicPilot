---
name: fpga-architecture-optimization
description: >-
  Code-level FPGA optimization for speed, area, and resource inference: critical-path reduction, pipelining, retiming, fanout reduction, resource sharing, BRAM/DSP/SRL mapping. Use to make RTL faster/smaller/timing-clean, or when reports show low Fmax, negative slack, or high LUT/FF/BRAM/DSP use.
---

# FPGA Architecture Optimization

FPGA optimization starts in RTL. Place-and-route can polish a design, but a
deep combinational cone, accidental priority chain, LUT-built memory, or
unregistered high-fanout control signal is a code-level architecture problem.

This skill is for **RTL authoring with timing / area in mind** —
preempting bottlenecks before they appear in reports. When a synth or
pnr report already shows negative slack or over-budget utilization, use
`fpga-timing-closure` (report-driven iteration) instead.

## Read the report before changing RTL

Do not optimize blindly. First classify the bottleneck:

- **Logic depth**: too many LUT levels, nested `if`, wide mux, adder/comparator
  chain, unbalanced reduction.
- **Routing delay / fanout**: high-fanout enables/resets, long cross-chip buses,
  poor locality.
- **Resource inference**: memory became LUTRAM instead of BRAM, multiplier
  became LUTs instead of DSP, shift register became FF chain.
- **Constraint issue**: missing clock, wrong generated clock, unconstrained I/O,
  false CDC path being timed as synchronous.
- **Protocol latency issue**: adding a pipeline stage might violate the
  interface unless valid/ready/backpressure is aligned.

## Speed optimization playbook

Apply one class of fix at a time and rerun the flow.

1. **Pipeline the critical path**. Add registers at natural boundaries
   (after multipliers, adders, mux trees, BRAM outputs, protocol stages). State
   the latency change and align valid/control signals.
2. **Balance operators**. Convert linear chains into balanced trees where the
   operation is associative (adder/reduction/mux tree). Pipeline tree levels if
   needed.
3. **Remove accidental priority**. A long `if/else if` chain infers priority.
   Use `case`, one-hot selects, or parallel decode when priority is not required.
4. **Move critical controls earlier**. Precompute enables/selects before the
   data path stage they control.
5. **Reduce fanout**. Register-duplicate high-fanout enables, reset releases,
   or state decodes per region/sub-block; let the tool replicate where possible.
6. **Use hard blocks intentionally**. Pipeline DSP inputs/outputs and code RAMs
   in the synchronous style expected by the vendor.
7. **Constrain correctly**. Generated clocks, multicycle clock-enable paths, and
   CDC false paths must be stated before timing numbers are trusted.
8. **Floorplan only after RTL fixes**. Use Pblocks/LogicLock/region constraints
   when locality is the problem or hard blocks must be clustered.

## Area optimization playbook

1. **Right-size datapaths**. Derive widths; do not carry extra bits through a
   pipeline unless the math requires them.
2. **Share expensive resources**. Time-multiplex multipliers/dividers/large
   adders when throughput allows; add a small scheduler/FSM.
3. **Prefer BRAM over registers for large storage** and LUTRAM/SRL for small
   shift/table structures when the target supports it.
4. **Avoid duplicated decode**. Register shared control results once.
5. **Remove unused flexibility**. Parameters/modes that are never used either
   cost logic or confuse synthesis.

## Memory and DSP inference rules of thumb

- Synchronous RAM read generally infers BRAM better than asynchronous read.
- Register BRAM address/control and often the output for timing.
- Avoid resetting large memories; reset valid bits/pointers instead.
- Multipliers map best to DSPs when widths fit the DSP primitive and pipeline
  registers are placed around the operator.
- A shift register without reset may infer SRL; adding reset to every stage can
  prevent SRL inference.

## Optimization contract

Before changing RTL, state:

```text
Target: <Fmax/area/resource goal>
Bottleneck evidence: <report path / metric>
Change: <pipeline / balance / share / constrain / floorplan>
Trade-off: <latency + area + interface impact>
Verification: <lint/sim/synth/pnr/GLS/LEC steps>
```

## Definition of done

The optimization is tied to a measured bottleneck, the latency/resource
trade-off is stated, control/data alignment is preserved, constraints are
correct, and the final report shows concrete improvement without breaking
simulation or equivalence.
