---
name: hardware-synthesis
description: >-
  Synthesize RTL to a gate/cell netlist and interpret synthesis reports. Use to synthesize, build, elaborate, get resource/utilization numbers, or generate a netlist/bitstream. For power/thermal/current route to hardware-power-analysis; use after simulation passes and before timing optimization.
---

# Hardware Synthesis & Build

Turn verified RTL into a netlist and report what it costs in resources. This is
where sim-clean-but-synth-dirty problems surface (latches, unsupported
constructs, multi-driven nets).

## Workflow

1. Confirm `sim` passed first (don't synthesize unverified RTL).
2. Run synthesis:
   ```
   python3 <flow>/logicpilot.py synth --config flow.toml
   ```
3. Read the JSON:
   - `status: fail` → read `tail`/`log`. Common causes: inferred latch,
     multi-driver, unsupported construct, missing module. Fix in RTL
     (`hardware-rtl-design`) and rerun. Do not "fix" by changing simulation.
   - `warnings` → the driver elevates synthesis red flags (inferred latch,
     multiple drivers) even on a returncode-0 run. Treat any such warning as a
     real defect before reporting success — do not claim pass from exit code.
   - `metrics` → utilization (`luts`, `ffs`, `bram`, `dsp`). Compare against
     the project budget. If over budget, this is a synthesis/area problem;
     iterate RTL/constraints or enter an optional back-end optimization skill if requested.
   - For anything beyond the headline numbers — confirming memory/DSP/FSM
     inference, spotting logic that was optimized away, or DRVs — read
     `references/report-reading.md`; the diagnostic detail is in the log, not
     the metrics.
   - Power is intentionally a separate stage/skill because meaningful numbers
     depend on switching activity, voltage, temperature, and implementation
     stage. Use `hardware-power-analysis` and run `power` when requested.
4. For a full build to bitstream, run the `pnr` stage (place/route + bitstream)
   or `all` for the whole pipeline:
   ```
   python3 <flow>/logicpilot.py all --config flow.toml
   ```

## Reading utilization

- Treat synthesis numbers as an estimate; post-P&R numbers are the truth.
- A design that's >70-80% full will be hard to route and close timing — flag it
  early rather than at `pnr`.
- Unexpectedly huge LUT/FF counts usually mean: accidental wide
  comb logic, unintended replication, a `* (* keep *)` blocking optimization,
  or a multiplier/divider that should be a DSP or pipelined.

## Measuring the shortest clock period (Fmax)

Do not get Fmax from simulation or an unconstrained report. Use static timing
with real clock constraints.

For a run constrained at period `T` (ns), read setup WNS:

`Tcrit ≈ T - WNS`
`Fmax_MHz ≈ 1000 / Tcrit`

This is valid only when clocks, generated clocks, false/multicycle paths, I/O
timing, and CDC assumptions are sane. Always say which stage produced the
number: post-synthesis is an estimate; FPGA post-route or ASIC signoff STA is
the authority.

If the user has a target period, run timing once. `WNS >= 0` means the target is
met; WNS is the margin.

If the user asks for minimum period:

1. Start from a tight but legal period, not 0 ns.
2. Run timing; compute `Tcrit = T - WNS`.
3. Re-run near `Tcrit`.
4. Iterate:
   - `WNS` positive and above tolerance: tighten.
   - `WNS` negative: loosen with a damped/bisection step.
5. Stop when `0 <= WNS < tolerance` (default `tolerance = 0.05 ns` if the user has not specified one).
6. Confirm with `period - epsilon`:
   - if it still passes, keep tightening;
   - if it fails, current `period` is the minimum within `epsilon`.

Use ns for periods/slack. Report both period and frequency, plus the timing
stage used.

## Toolchain notes

The `synth` command comes from the active project stage definition. The plugin
does not prescribe a synthesis tool. Run `logicpilot.py --tools --config
flow.toml` to see which local candidates are available and which stage the
current workspace can run. Always go through the `synth` stage so results come
back as one consistent JSON shape.

### Recommended synthesizer by target (advisory)

This is the project's preferred ordering when multiple candidates would all
work. **Not enforced** — when a recommended tool isn't installed, fall back
to whatever IS, and report what ran (the JSON `tool` field).

| Target | Recommended tool | Fallback (open) | Why |
|---|---|---|---|
| **FPGA** (Xilinx/AMD) | **vivado** | yosys + nextpnr | Vivado understands the device-specific primitives (URAM, GTH, etc.) and produces a real bitstream. Yosys can synth but you still need the vendor for backend. |
| **FPGA** (Intel/Altera) | **quartus_sh** | yosys + nextpnr | Same reasoning. |
| **ASIC** | **dc_shell** (Design Compiler) | yosys | DC is the industry-standard sign-off synthesizer; yosys is fine for exploration but not for tape-out. |
| Anything when neither is installed | **yosys** | — | Always available, runs anywhere, good for getting *some* number. State clearly that yosys numbers are exploratory, not authoritative. |

Decision rule for the agent:
1. Look at the project target (`[project].target` or infer from preset).
2. Pick the recommended tool for that target.
3. If missing, fall back to the next-best installed candidate.
4. **Always quote in the report**: "synthesized under yosys (Vivado not
   installed; numbers are exploratory)". Never let "passed under yosys"
   sound equivalent to "passed under Vivado" for an FPGA project.

To wire a licensed synthesizer, redeclare the `synth` stage candidates in
`flow.toml` — see flow.toml.example.

## Definition of done

`synth` status `pass`, utilization within device budget, no latch/multi-driver
warnings. Report the resource summary, then proceed to timing. If power is in
scope, do not infer it from utilization alone; run the `power` stage or state
that no power stage/report is configured.
