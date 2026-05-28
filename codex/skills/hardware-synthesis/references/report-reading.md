# Reading a synthesis report

The driver parses the headline numbers (`luts/ffs/bram/dsp`, `fmax_mhz`,
`wns_ns`) into `metrics` and elevates latch / multi-driver red flags into
`warnings`. Everything else lives in the raw log (`tail`/`log`). Read it in this
order — the diagnostic gold is in the messages, not the numbers.

## 1. Inference report — did it build the hardware you intended?

The single most useful thing in a synth log. Check:

- **Latches.** Any inferred latch is almost always a bug: an incomplete
  `if`/`case` (missing `else`/`default`) or a missing assignment. (The driver
  already flags this in `warnings`.) Fix in RTL, do not waive.
- **Memory inference.** Did your array become a **BRAM** or **distributed/LUT
  RAM**, and is that what you wanted? An async-read or odd-width array often
  falls back to LUTRAM and blows up area. yosys prints memory mapping; vendors
  print "RAM inferred"/"Block RAM".
- **DSP / multiplier inference.** A `*` should usually map to a DSP block. If it
  mapped to LUTs, you have a huge, slow multiplier — pipeline it or force DSP.
- **FSM extraction / encoding.** Vendors report extracted state machines and the
  encoding chosen (binary/one-hot); confirm state count matches your design.

## 2. Optimized-away logic — a quiet bug signal

Synthesis removes unconnected, constant, or unreachable logic. A register or
whole block that "disappeared" usually means a wiring mistake (tied off,
unconnected output, dead branch). Search the log for removed/pruned/unused
nets and registers and reconcile each against intent. Silent removal is more
dangerous than an error.

## 3. Utilization / area

- Treat synth numbers as an **estimate**; post-place-and-route numbers are the
  truth (routing changes packing).
- >70–80% full → hard to route and close timing; flag early, not at P&R.
- Unexpectedly huge LUT/FF: accidental wide combinational logic, unintended
  replication, a `keep`/`dont_touch` blocking optimization, or a
  multiplier/divider that should be a DSP or pipelined.
- Per-module/hierarchy breakdown (vendor) finds the heavy block.

## 4. Timing estimate

Post-synthesis Fmax/WNS is optimistic — it lacks routing delay (dominant in
FPGAs). Use it as an early indicator only; real timing comes from the `pnr`
stage. A negative synth-time WNS is already a bad sign and the driver flags it.
The shortest period is read from one run, not a sweep: `period = T_target − WNS`,
`Fmax = 1/(T_target − WNS)` (see the two-case procedure in the synthesis skill).
**No clock constraint → no meaningful Fmax**: make sure the design has one (see
`hardware-constraints` for authoring SDC/XDC/PCF).

## 5. Design-rule violations (mostly ASIC / vendor)

Max transition (slew), max capacitance, max fanout. High-fanout nets and slow
transitions hurt timing and power; the synth `report_constraint` (ASIC) or
vendor DRC report lists them. On the open FPGA flow these are largely deferred
to P&R.

## 6. Power (separate report path)

Do not treat utilization as a power report. Power requires its own assumptions:
activity source, clock frequencies, voltage, temperature, and design stage. When
the project defines a `power` stage, run:

```bash
python3 <flow>/logicpilot.py power --config flow.toml
```

Then use `hardware-power-analysis` to interpret `metrics`, `assumptions`, and
`warnings`. A vectorless/default estimate is useful for early comparison only;
budget decisions need representative SAIF/VCD or signoff activity.

## Quick triage

`status: fail` → read `tail` for the first error (latch / multi-driver /
unsupported construct / missing module), fix in RTL, rerun. `status: pass` but
`warnings` present → treat the warning as a real issue before reporting success.
`pass` and clean → report utilization vs budget and the (estimated) timing
headroom, then proceed.
