# Brainstorm round (before any decision Q&A)

Run this round before Round 0 (scope), before any implementation Q&A. The
purpose of Brainstorm is to **map out the design space** —— what kind of
hardware is this, what does it interface with, what are the real risks and
constraints —— before starting to converge on concrete implementation
options.

Without brainstorm, the default degenerates into "asking questions in the
SPI-master mold", which produces bad designs for clocking subsystems, BIST
controllers, mixed-signal interfaces, and anything that doesn't fit the
"CPU-attached digital IP" template.

Style is the same as other LogicPilot rounds: multiple-choice + ★
recommended + one-line reason. The **only** difference is each question
ends with `Other — <free text>` (see the "Other escape hatch" principle in
`principles.md`) —— the design space at the brainstorm stage is too wide to
be pre-enumerated exhaustively.

## 6 categories —— split into two batches, 3 questions each

```
1. Design nature —— what kind of hardware is this?
   A) Datapath / compute pipeline — DSP, NN, crypto core, codec
   B) Control / FSM / protocol engine — arbiter, scheduler, link-layer
   C) Datapath + control hybrid — peripheral IP, CPU subsystem
   D) Clocking / timing structure — PLL+clkgen, retiming, synchronizer chain
   E) Analog-adjacent interface — ADC/DAC frontend, SerDes phy, sensor
   F) Test / DFT — BIST, scan chain, ATPG hook
   G) Power management — PMU, retention, level shifter, DVFS
   H) RF — TX/RX frontend, modulator / demodulator
   I) Other — <describe in plain language>

2. Host context —— how is this block integrated into the system?
   A) CPU + memory-mapped bus (AXI/APB/AHB/Wishbone) ★ common for IP cores
   B) Standalone streaming — data in, data out, no CPU
   C) Standalone control — signals out, sensors in, no CPU
   D) Chip-to-chip / off-chip interface
   E) Network / packet-based
   F) No host (runs once at power-on, e.g., BIST)
   G) Other — <describe>

3. Primary risk —— what is most likely to bite?
   A) Timing closure / Fmax
   B) Area / fitting on the target die
   C) Power budget
   D) Verification coverage / state space
   E) Numerical correctness (fixed-point, rounding, saturation)
   F) Signal integrity / analog matching / metastability
   G) Interop with external spec or reference silicon
   H) Other — <describe>

(After the user answers 1–3, enter the second batch:)

4. Hard constraints —— what is non-negotiable?
   A) Target platform (specific FPGA part / ASIC node)
   B) Latency budget
   C) Area budget
   D) Power budget
   E) Interop spec (must be bit-exact with an external counterpart)
   F) Schedule (must ship in phases)
   G) Side-channel / security posture
   H) Other — <describe>

5. Alternative directions —— what other implementations did you consider?
   What is the verdict on each?
   The agent proposes 2–4 plausible alternatives based on Q1–Q4 answers,
   each with a verdict slot:
   A) <alternative 1> — verdict: chosen / rejected / deferred / unknown
   B) <alternative 2> — verdict: chosen / rejected / deferred / unknown
   C) Other — <alternative name the agent didn't list> + verdict

6. Explicitly out of scope —— what does this design explicitly **not** do?
   The agent proposes 2–4 candidate OOS items based on Q1–Q4 (e.g.,
   "runtime dynamic reconfiguration" for a clocking block; "constant-time
   + masking" for a v1 crypto block), the user picks which to confirm and
   adds their own. Expect more `Other` items than pre-enumerated ones in
   this category —— that's normal.
```

## Output: `docs/brainstorm.md` (soft, not gate-enforced)

Loose structure —— one paragraph per category, recording the user's answers
verbatim including their `Other`. plan-check does **not** require this file
to exist. But its absence is a smell: subsequent implementation Q&A
degenerates into default-shape questions, even when the design nature is
unusual.

## What changes after a good brainstorm

Brainstorm answers steer the subsequent **implementation Q&A**:

- **Design nature** answers determine which Tier-0 categories to ask. A
  clocking subsystem has no memory map; a BIST controller has no streaming
  backpressure; a PMU has no host bus in the usual sense.
- **Primary risk** answers re-rank the ★ recommendations. If the risk is
  timing closure, the pipeline depth ★ leans conservative; if the risk is
  area, ★ leans dense.
- **Out-of-scope** list pre-closes a class of questions. If the user says
  "no CPU host", don't ask about CSR ergonomics anymore.

For a full exemplar see `dialogue-brainstorm.md` (a clocking subsystem ——
deliberately picked a design that is **not** a typical CPU-attached IP, to
show how brainstorm clarifies the design nature before any decision Q&A).
