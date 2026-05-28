# Exemplar dialogue —— streaming compute (FIR filter)

> **Block scope** —— a single IP. Outputs `docs/{spec,uarch,plan}.md`. For
> project scope flow (multiple subsystems, arch.md + subsystem tree), see
> `dialogue-soc-mldsa.md`.
>
> EXEMPLAR, not a template. Shows the questioning style for a pure streaming
> block. The genuine ambiguities are precision, throughput, and reset behavior
> —— not CSR (there is no CSR here at all).

## User brief

> "16-tap FIR filter, AXI-Stream in/out, signed input, 100 MHz."

## Agent analysis (not shown to the user)

Already pinned down: 16 taps, AXI-Stream, signed, 100 MHz. To clarify: input
bit-width? Output bit-width and saturation strategy? Coefficient source
(static / runtime-loadable)? Coefficient precision? Throughput target (one
sample per cycle, or slower)? Pipeline depth vs latency trade-off? Reset
behavior when the delay line is partially filled? Is tlast / tuser passed
through? Backpressure depth?

## Round 1 —— data types and precision (the biggest source of hidden bugs)

```
1. Input data width:
   A) 16-bit signed  ★ (typical audio / sensor)
   B) 12-bit signed
   C) Parameterized 8..24

2. Coefficient precision:
   A) 16-bit signed, Q1.15 fixed-point  ★
   B) 18-bit (Xilinx DSP friendly)
   C) Parameterized

3. Internal accumulator:
   A) Full-precision (input + coeff + log2(taps)) = 16+16+4 = 36-bit  ★
      cannot overflow during accumulation
   B) Saturated to 32-bit per MAC
   C) Symmetric-coefficient optimization

4. Output width + saturation:
   A) 16-bit signed, saturate on overflow  ★
   B) 16-bit signed, wrap on overflow (cheaper but produces an audible click)
   C) 24-bit signed, no saturation needed

Pick A/A/A/A or some other combination?
```

User: A/A/A/A.

## Round 2 —— coefficient source and reset

```
5. Coefficient source:
   A) Compile-time parameter (16-element 16-bit array)  ★
      cheapest, fixed response
   B) Loaded at runtime over a separate AXI-Stream "coeff" port
   C) Loaded over a small AXIL slave (introduces a CSR plane)

6. Reset behavior on delay line:
   A) Clear the delay line on aresetn; output 0 until 16 samples
      have accumulated  ★
   B) Do not reset the delay line (keep the residue from the previous run)
   C) After reset, emit a single-cycle pulse on tlast

7. Throughput target:
   A) Process 1 sample per aclk cycle (one MAC per cycle, fully pipelined)  ★
   B) Process 1 sample every 16 cycles (reuse a single MAC)
   C) Parallelism configurable via parameter

Pick A/A/A?
```

User: A/A/A.

## Round 3 —— AXI-Stream details

```
8. Backpressure:
   A) Propagate tready backwards with 1 cycle of latency, no internal
      buffering  ★ (simplest)
   B) Small 4-stage skid buffer to mask downstream stalls
   C) Fully elastic buffer (depth = tap_count)

9. tlast / tuser:
   A) Pass through unchanged, aligned with the output sample
      (delay = tap_count - 1)  ★
   B) Drop tlast/tuser entirely
   C) Reset the delay line on tlast

10. First-sample handling:
    A) Begin emitting output on the same cycle the 16th input arrives,
       latency = 16 cycles, prior outputs are 0  ★
    B) Tag the first 16 samples with a "warmup" tuser flag
    C) Silently drop the first 15 outputs

Pick A/A/A?
```

User: A/A/A.

## What ends up written into spec.md

The final shape includes the following sections (none of them mandated by a
template —— all of them emerged naturally from the questioning):

- Function
- Interfaces (s_axis, m_axis —— 2 lines, simpler than SPI's 6)
- Clocks (1 line)
- Resets (1 line, but with a NOTE about delay-line clear semantics ——
  this one comes from Q6)
- **Fixed-point precision** (input Q1.15, full-precision accumulator,
  output Q1.15 saturated —— this section exists because Round 1 required it)
- Performance targets (Fmax, throughput = 1 sample/aclk,
  latency = 16 cycles)
- Parameters (TAPS=16 fixed, or TAPS as a parameter if the user wants it)
- Coefficients (array literal or load mechanism)
- Failure modes (saturation on overflow —— this is a *decision*, not a bug)
- Assumptions (input rate ≤ aclk rate; fixed-point so no NaN/Inf)

No CSR section. No IRQ. One extra fixed-point section that the SPI exemplar
did not have. Shape follows the design.

## File-list allocation in uarch.md

| path | role | test | artifact |
|------|------|------|----------|
| rtl/fir_top.sv         | top integration   | integration                          | covered by tb/fir_smoke_tb.sv (named "golden_response_32samp") |
| rtl/coeff_rom.sv       | coefficient ROM   | integration                          | covered by tb/fir_smoke_tb.sv (named "rom_readout_matches_param") |
| rtl/delay_line.sv      | 16-stage delay    | property/invariant                   | output[N] == input[N-16]; reset clears all stages |
| rtl/mac_array.sv       | parallel MAC      | reference-model + property/invariant | numpy golden: convolve(coeffs, window) Q1.15 quantized; after the 16-sample warmup, output_valid asserts every aclk |
| rtl/accumulator_sat.sv | saturation        | reference-model                      | numpy golden: clip(acc, -2^15, 2^15-1) |
| rtl/axis_io.sv         | AXIS skid + tlast | property/invariant                   | no data loss; tlast/tuser aligned with the output sample (16-cycle delay) |

`mac_array` carries both kinds of obligation: the numeric output is
determined by inputs + coeffs (reference-model), and the pipeline-utilization
rule requires "after warmup, every aclk produces one output and never
stalls" (invariant). Reference-model alone could pass a regression that
drops one in every N outputs.

`accumulator_sat` is reference-model only because it is pure combinational
saturation —— there is no timing rule to enforce.

`coeff_rom` is integration only because for compile-time fixed coefficients
(Round 2 picked option A), the ROM is a trivial table —— the contents are
fixed, and being observed by the smoke test is enough. If Round 2 had picked
the runtime-loadable option, this row would flip to
`reference-model + property/invariant` (golden = expected ROM contents for
any load sequence; invariants = no loads allowed during operation).

## Why this pattern

- Round 1 (precision) goes first because **every** downstream sizing
  decision depends on it. Pipeline depth, BRAM vs DSP inference, fmax ——
  the moment the user wants 24-bit instead of 16-bit, all of them change.
- Round 2 (coefficient source) decides whether this block needs an AXIL
  plane at all. If runtime loading is chosen, the spec grows an entire CSR
  section.
- Round 3 (tlast/tuser) is where downstream integration bugs hide. The vast
  majority of "the FIR runs fine on its own but breaks in the system"
  problems trace back to tlast misalignment.
