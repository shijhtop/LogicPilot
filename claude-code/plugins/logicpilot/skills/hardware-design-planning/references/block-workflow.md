# Block-scope workflow

Use when scope = block. Three documents under `docs/`: `spec.md`, `uarch.md`,
`plan.md`. SKILL.md gives the outline; this file gives the full steps + refined
ambiguity categories.

## Steps

1. **Read the brief.** Surface every concrete claim and every blank spot (do
   not show them to the user yet).

2. **Classify the ambiguity.** Generic categories that apply to any block:

   - Interface and protocol semantics (handshake, backpressure, error response)
   - Clocks (count, source, asynchronous relationships, gating)
   - Reset (sync vs async, polarity, scope per domain)
   - Performance targets (Fmax, throughput, latency, jitter)
   - Failure modes (overflow, underflow, illegal input, timeout, recovery)
   - Configurability (parameter vs hardcoded, legal range)

   More specific categories worth checking per block type — **but don't be
   boxed in by this list**, ask about whatever pops out of the brief:

   - **Register-mapped peripherals**: CSR layout, IRQ semantics, per-bit W1C
     vs RW vs RO, byte vs word access width
   - **Streaming blocks** (AXI-Stream / valid-ready): backpressure depth,
     mid-packet stall behavior, packet boundaries, framing
   - **Bridges / adapters**: transaction mapping, outstanding count, response
     code translation
   - **Compute blocks**: fixed-point / floating-point, saturation vs
     wraparound, rounding mode, pipeline depth vs latency tradeoff
   - **Multi-clock / CDC**: per-signal synchronizer choice, FIFO depth,
     handshake details, reset domain crossing
   - **Memory controllers**: refresh, ECC, scrub, partial-word semantics

3. **Frame each ambiguity as a multiple-choice question**, in the format
   given by the "no open-ended questions" section of `principles.md`.

4. **3–5 questions per batch.** Adjust subsequent batches based on the
   user's answering pattern.

5. **Record decisions live into `docs/spec.md`.** Structure follows what the
   design needs — a peripheral naturally grows a CSR table, an FFT naturally
   grows a fixed-point precision section, a bridge naturally grows a
   transaction mapping table.

6. **Move to microarchitecture.** Once interfaces and assumptions are signed
   off, `docs/uarch.md` captures:

   - Block partitioning (submodule tree)
   - Datapath / control separation
   - FSM sketches
   - Pipeline depth
   - Memory inference choice (distributed vs BRAM / DRAM)
   - File list table (for per-module test assignment — see the "per-module
     test assignment" section of SKILL.md)

7. **Write `docs/plan.md` as a checkbox execution log.** Each `- [ ]` is a
   concrete deliverable (a file, a stage that runs end-to-end, an assertion
   to write). Empty plan = no plan, won't pass the plan-check MUST gate.

## Handoff conditions

Only hand off to `hardware-rtl-design` after the 5 MUST conditions in
SKILL.md's "Definition of done" are satisfied.

## Exemplar

Look up `dialogue-*.md` by block shape:

- `dialogue-peripheral-spi.md` — CSR-mapped peripheral
- `dialogue-streaming-fir.md` — streaming compute
- `dialogue-bridge-axil-apb.md` — protocol bridge
- `dialogue-async-fifo.md` — CDC FIFO
- `dialogue-crc-engine.md` — pure compute block

They are **exemplars, not templates** — learn the style, don't copy the
structure. Your brief may sit well outside the exemplar set (PMU, ADC
front-end, ML systolic array, SerDes, …); the workflow is the same, the
questions differ; the brainstorm round helps you identify which questions
to ask.
