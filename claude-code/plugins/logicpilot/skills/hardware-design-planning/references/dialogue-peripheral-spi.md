# Exemplar dialogue —— register-mapped peripheral (SPI master)

> **Block scope** —— single IP. Outputs `docs/{spec,uarch,plan}.md`. For
> project-scope flow (multi-subsystem, arch.md + subsystem tree), see
> `dialogue-soc-mldsa.md`.
>
> EXEMPLAR, not a template. Demonstrates the questioning style for a
> typical CPU-attached peripheral. Do not copy this question set verbatim
> —— derive your own from your own brief.

## User brief

> "Build me a 4-CS SPI master, host side is AXI4-Lite, aclk 100 MHz,
> both TX and RX need FIFOs."

## Agent analysis (not shown to the user)

Concretely known: 4 CS, AXIL slave, 100 MHz, TX+RX FIFO.
Gaps: SPI mode? Bit-rate range? Transfer width? FIFO depth? Does CS
auto-deassert between bytes or does SW hold it? IRQ semantics? AXIL
response policy? Error handling for FIFO underflow / overflow /
selecting the wrong CS? Reset strategy? Is the CS count parameterizable
or fixed at 4?

## Round 1 —— interface essentials

```
1. SPI mode:
   A) Mode 0 only (CPOL=0, CPHA=0) —— covers the vast majority of slaves, simplest  ★
   B) All 4 modes supported, selected at runtime via CSR
   C) Mode 0 + Mode 3 only

2. Transfer width:
   A) 8-bit only  ★
   B) 8/16/32-bit, selectable per transfer
   C) Arbitrary bit count, up to 32

3. CS behavior between bytes:
   A) SW-managed: assert/release CS by writing the CS_CTRL register  ★
   B) Auto-deassert for one cycle between bytes
   C) Auto-deassert at end of burst (requires burst-length CSR)

4. NUM_CS:
   A) Parameter, default 4, range 1..16  ★
   B) Fixed at 4
   C) Parameter, no upper bound (synthesis tool decides)

Pick A/A/A/A, or change any of them?
```

User: A/A/A/A.

## Round 2 —— AXIL response + IRQ

```
5. AXIL write response timing:
   A) bvalid in the same cycle wlast is accepted, BRESP=OKAY  ★
   B) bvalid delayed by 1 cycle
   C) Wait until the register actually takes effect

6. AXIL response code on writes to RO registers:
   A) BRESP=OKAY, write silently dropped  ★
   B) BRESP=SLVERR
   C) BRESP=DECERR

7. IRQ semantics:
   A) Single level-high irq_o, status bits in IRQ_STAT are sticky W1C  ★
   B) Pulse irq_o once per event
   C) Multiple irq lines (one per source)

8. Reset:
   A) Async assert / sync deassert, on aclk  ★
   B) Fully synchronous
   C) Pure asynchronous

Pick A/A/A/A?
```

User: A/A/A/A.

## Round 3 —— failure modes

```
9. TX write to a full FIFO:
   A) Silently dropped, set STATUS.TX_OVF (SW must poll or enable IRQ)  ★
   B) BRESP=SLVERR, transaction rejected
   C) Block bvalid until space is available (deadlock if SW never drains)

10. RX read from an empty FIFO:
    A) Return 0x0, set STATUS.RX_UDF
    B) BRESP=SLVERR  ★ (SW bugs should be loud)
    C) Block (deadlock risk)

11. Bit-rate (SCK) configuration:
    A) 16-bit CLKDIV CSR, SCK = aclk / (2 × CLKDIV), CLKDIV min 1 → 50 MHz  ★
    B) Fixed aclk/4
    C) Enumerated preset rates

Pick A/B/A?
```

User: A/B/A.

## What gets written into spec.md after these 3 rounds

The agent now has enough decisions captured to draft `docs/spec.md`.
The structure it is most likely to pick:

- Function (1 paragraph)
- Interface (port table —— 7 columns naturally emerge: port/dir/width/proto/
  backpressure/clock/reset)
- Clock (1 line —— aclk@100MHz)
- Reset (1 line —— aresetn, async / active-low)
- **CSR map** (about 10 rows —— this section appears because the design
  carries AXIL; no template is forcing it)
- Performance targets (Fmax, max SCK, AXIL latency, IRQ latency)
- Parameters (NUM_CS, FIFO_DEPTH, CLKDIV_WIDTH)
- Failure modes (TX overflow, RX underflow, RO writes —— all from Round 3)
- Assumptions (single clock, SPI slave provides reasonable hold time, etc.)

The CSR map and the "failure modes" sections are **not in any template**
—— they appear because the design needs them and the agent asked.

## Allocation in the uarch.md File list

The end of uarch.md lands on a per-module test assignment. For this SPI
design, the File list after decomposition looks roughly like:

| path | role | test | artifact |
|------|------|------|----------|
| rtl/spi_top.sv        | top integration   | integration                          | Covered by tb/spi_smoke_tb.sv: 10 CSR R/W + 1 full transfer |
| rtl/axil_decode.sv    | address decode    | integration                          | Covered by tb/spi_csr_tb.sv: all 10 CSR addresses |
| rtl/spi_csr.sv        | register file     | property/invariant                   | Only 1 bit permits W1C; RO blocks writes; RW round-trips consistently |
| rtl/spi_clk_div.sv    | SCK divider       | reference-model                      | python: compute SCK toggle pattern from CLKDIV value |
| rtl/spi_bit_engine.sv | bit serializer    | reference-model + property/invariant | python: compute MOSI sequence from byte; FSM legality, CS hold |
| rtl/spi_tx_fifo.sv    | TX FIFO           | property/invariant                   | ordering, no loss, full/empty timing |
| rtl/spi_rx_fifo.sv    | RX FIFO           | property/invariant                   | ordering, no loss, full/empty timing |
| rtl/spi_irq.sv        | interrupt logic   | property/invariant                   | sticky bits, mask, level-high until W1C |

`spi_bit_engine` carries **two** obligations: the MOSI bit pattern for
any input byte is deterministic and computable (reference-model), and
the FSM has temporal rules (CS does not switch mid-transfer, no illegal
states appear). Doing only one of the two would miss an entire class of
bugs.

`axil_decode` and `spi_top` go integration-only because they have no
independent state or transformations —— they just wire things together.
Each one names the specific top-level TB / coverage point that exercises
it; writing only "skip" is not allowed.

## Why this pattern

- Round 1 pins down the interface scope before doing anything else;
  otherwise every time the user revises the CS behavior, reset and CSR
  decisions cascade.
- Rounds 2–3 are independent of each other; if the user reverses a
  Round 2 decision, the Round 3 questions remain valid.
- The "★ recommended" marker lets users who trust the agent's judgement
  reply "all defaults" in one line.
- The agent never has to invent an answer. Every line in the spec is
  traceable to a user decision.
