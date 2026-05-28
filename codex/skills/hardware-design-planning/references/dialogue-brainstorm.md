# Exemplar dialogue —— Brainstorm round (clocking subsystem)

> EXEMPLAR (example), not a template. Shows a hardware design **brainstorm round**
> that does **not** fit the typical "datapath + CSR + AXIL" paradigm —— a clocking
> subsystem with PLL, clock mux, divider, and reset synchronizers. The purpose of
> the brainstorm round is to *first* clarify the essential nature of the design,
> so that the follow-up implementation Q&A can ask the right questions instead of
> defaulting to "ask everything in SPI-master style".

## User brief

> "I need a clocking block for my SoC. The input is a 25 MHz crystal, and it
> needs to generate a 100 MHz core clock, a 50 MHz IO clock, and a 200 MHz DDR
> clock. It also needs a reset synchronizer for each output domain. The target
> platform is Xilinx Artix-7."

## Agent analysis (not shown to the user)

Concrete known information: generate 4 output clocks from a 25 MHz input,
7-series target, reset sync required. Gap: this is **not** an IP core, not a
streaming compute block, and not a CSR-bearing peripheral. It is a clocking /
timing structure. Running the standard "SPI/peripheral" question set would
produce a pile of garbage —— there is no SPI mode, no FIFO depth, no AXIL
response policy here. We must brainstorm first to identify the *correct*
downstream question set.

## Brainstorm Round 1 —— design nature, host context, primary risks

Every question carries `Other — <free text>` as the last option (following the
"Other" escape-hatch principle —— the design space at the brainstorm stage is
too wide to enumerate in advance).

```
1. Design nature:
   A) Datapath / compute pipeline
   B) Control / FSM / protocol engine
   C) Mixed datapath + control (peripheral IP, CPU subsystem)
   D) Clocking / timing structure —— PLL, clkgen, retiming, sync chain  ★
      Matches the brief exactly
   E) Analog-adjacent interface —— ADC/DAC, SerDes, sensor front-end
   F) Test / DFT
   G) Power management
   H) RF
   I) Other —— <describe in plain English>

2. Host context —— how is this block integrated?
   A) CPU + memory-mapped bus
   B) Standalone streaming (data in / data out)
   C) Standalone control —— provides clocks and resets to other blocks,
      no CPU host, no streaming  ★
      The standard role of a clocking subsystem
   D) Chip-to-chip / off-chip
   E) Network
   F) No host —— runs once at power-on
   G) Other —— <describe>

3. Primary risk —— what is most likely to bite?
   A) Timing closure / Fmax
   B) Clock-mux glitch  ★ classic clocking pitfall, frequently overlooked
   C) PLL lock time / phase noise / jitter spec
   D) Reset-domain crossing —— wrong polarity in the sync chain,
      wrong depth, releasing before the clock is stable
   E) Area
   F) Power
   G) Verification scope
   H) Other —— <describe>
```

User answers: 1**D**, 2**C**, 3**B + D** (both selected —— mux glitch and
reset-domain crossing are both real concerns; "we got bitten by both on the
last project").

Free-text addition under Q3: "We also need CDC between the 200 MHz DDR clock
and the 100 MHz core —— we have a few status bits going from the DDR controller
back to the core that need clean synchronizers."

## Brainstorm Round 2 —— constraints, alternatives, OOS

```
4. Hard constraints:
   A) Target platform —— Xilinx Artix-7 xc7a200t  ★ must use MMCM
   B) Latency budget —— reset deasserted within 100 ns of PLL lock  ★
   C) Area —— not important at this layer
   D) Power —— not important at this layer
   E) Interop spec —— input crystal 25 MHz ±50 ppm  ★ vendor part fixed
   F) Schedule
   G) Side channel / security
   H) Other —— <describe>

5. Alternative implementations (agent proposes 3 based on Q1–Q4):
   A) Single MMCM with 4 output clocks  ★
      —— cheap, all sourced from the same VCO, phase relationships
      locked automatically
   B) Two MMCMs in cascade —— extra PLL stage, more jitter, more area
   C) One MMCM + one PLL —— mixes primitives, no real advantage
   D) Other —— <propose another approach with a verdict (in/out/deferred)>

6. Explicit out of scope (agent proposes 4 likely OOS items):
   A) Runtime dynamic reconfiguration of clock ratio —— deferred to v2
   B) Spread-spectrum modulation —— not needed for this product
   C) Clock-domain power gating —— belongs to a separate PMU subsystem
   D) Clock-skew controller —— FPGA BUFG balancing already handles it
   E) Other —— <propose additional OOS items>
```

User answers:
- Q4: **A + B + E** (target, reset latency, crystal spec —— all hard constraints)
- Q5: **A** (single MMCM cascade)
- Q6: **A + B + C + D** (all 4 OOS items confirmed)
- Q6 free text: "Also OOS —— no support for an auxiliary 32 kHz always-on clock;
  that one is handled separately by the PMU."

## Output: `docs/brainstorm.md` (skeleton)

```markdown
# Brainstorm —— clocking subsystem v1

## Design nature
Clocking / timing structure (1D). Not a datapath, not a peripheral.

## Host context
Standalone clock distribution (2C). No CPU bus, no streaming. Provides
clocks and resets to other blocks inside the SoC.

## Primary risks
Clock-mux glitch (3B) and reset-domain crossing (3D). Both must be managed.
Also flagged: status-bit CDC from 200 MHz DDR back to 100 MHz core.

## Hard constraints
- Platform: Xilinx Artix-7 xc7a200t (MMCM, not generic PLL)
- Reset latency: deasserted within 100 ns after PLL lock
- Input crystal: 25 MHz ±50 ppm (vendor fixed)

## Preferred direction
Single MMCM cascade with 4 outputs (5A). Shared VCO, with phase
relationships locked automatically across outputs.

## Out of scope
- Dynamic reconfiguration of clock ratio
- Spread-spectrum modulation
- Power gating of clock domains (PMU's responsibility)
- Skew controller (handled by FPGA BUFG)
- 32 kHz always-on clock (PMU's responsibility)
```

## What this changes for downstream Q&A

Because the brainstorm pinned down `Design nature = clocking`,
`Host context = standalone`, and `Primary risk = mux glitch + reset CDC`, the
follow-up implementation Q&A **will**:

**Not ask** (questions a typical IP would default to):

- "SPI mode 0 or support all 4 modes" —— there is no SPI
- "AXIL response code on PSLVERR" —— there is no AXIL
- "TX/RX FIFO depth" —— there are no FIFOs
- "CSR W1C or RW semantics" —— there are no CSRs
- "AXI-Stream backpressure" —— there is no stream

**Will ask** (questions specific to a clocking subsystem):

- "Glitch-free mux primitive: BUFGCTRL  ★ vs gate-then-mux vs LUT-based"
- "Reset synchronizer depth: 2-FF, 3-FF  ★ or 4-FF; chosen per output
  domain, or worst-case across the board?"
- "MMCM lock signal: gate downstream reset directly, or pass it through a
  stable-for-N-cycles counter?"
- "Status-bit CDC from 200 MHz DDR → 100 MHz core: 2-FF + Gray  ★ for
  multi-bit, single 2-FF for single-bit (decided per signal)"
- "Output BUFG instantiation: one BUFG per output, or BUFGCE for
  gateable outputs?"
- "PLL lock detection: trust the MMCM `LOCKED` pin, or add a
  consecutive-clean-cycles filter?"

Tier-0 Q&A categories that will apply:

- **Partition** (1 PLL + 1 mux array + 4 reset sync + 1 CDC slice → 4
  components —— the heading `## Components` fits this design's vocabulary
  better than `## Subsystems`)
- **Clock plan** (intrinsic: this *is* the entire subsystem)
- **Reset plan** (4 output-domain resets, all synchronized from a single
  input aresetn into each domain on export)
- **Platform target** (already pinned: Artix-7 + MMCM primitive)

Categories that will be **skipped**:

- **Top-level bus / fabric** —— no host bus
- **Memory map** —— nothing host-visible in memory
- **Interrupt routing** —— no events to report to the host
- **Power / security domains** —— single-domain design

## Why this pattern

- **Brainstorm is not "let's chat".** It is structured multiple-choice Q&A,
  with the **same** discipline as the implementation rounds. The only
  relaxation is that every question carries an `Other` free-text option ——
  necessary because the design space is wider than any prebuilt list.
- **The `Other` escape hatch matters most at this stage.** The user's
  free-text additions ("DDR↔core CDC is also a concern", "32 kHz clock
  is the PMU's job") and OOS items are decisions the agent could never
  propose; only the user knows them.
- **The brainstorm output drives the categories, alternatives, and ★
  recommendations of the downstream Q&A.** Without it, the agent would
  ask SPI/peripheral questions of a clocking subsystem —— which is exactly
  why generic plan-mode tools fail on non-mainstream hardware.
- **plan-check does not require `brainstorm.md`.** It is a soft stage.
  But if you skip it on an atypical design, the quality of the follow-up
  implementation Q&A will suffer; its absence is a "smell" to the
  reviewer rather than a hard failure.
