# cdc_top — async FIFO demo

This is a LogicPilot demo project that exercises the multi-clock /
CDC paths of the driver. It is **not** an industrial-strength FIFO.

## Goal

Verify that LogicPilot can:

- run a complete front-end pipeline on a multi-clock SystemVerilog project
- recognize the two legitimate gray-counter CDC crossings in `async_fifo`
- not flag the synchronizer flops as multi-driver under
  `--experimental-ast`
- produce a `pass` JSON envelope with no `[DEPRECATION-WILL-FAIL-...]` warnings

## Subsystems

- [x] `sync_2ff` — generic 2-flop synchronizer (parameterised width)
- [x] `async_fifo` — gray-pointer async FIFO, depth 8, width 8
- [x] `cdc_top` — wraps `async_fifo` as the project top module
- [x] testbench drives both clocks at different rates (100 MHz / 37 MHz)

## CDC inventory

See `docs/cdc-inventory.json`. Two crossings, both gray-coded,
both verdict `safe`. `set_clock_groups_declared: true` because in a
real project we would emit `set_clock_groups -asynchronous` for STA.

## Done when

- [x] `plan-check` passes
- [x] `audit` passes with zero high-severity findings
- [x] `tb-audit` passes (TB has self-check + LOGICPILOT_SEED marker)
- [x] `cdc-check` passes
- [x] `sim` runs to completion with a PASS line
- [x] `synth` produces a netlist with no inferred latches

## Non-goals

- Industrial-grade FIFO depth / throughput
- Real bitstream generation (the `pnr` stage requires an icepack flow
  not enabled in this demo)
- Power analysis (no SAIF is generated; activity is vectorless)
