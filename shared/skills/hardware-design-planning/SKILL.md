---
name: hardware-design-planning
description: >-
  Complete the "pre-alignment" for any HDL design before writing RTL — single
  block IP or multi-module project. Through guided multiple-choice Q&A, expose
  every ambiguity in the user brief and pin it down as a decision. Two scopes:
  block (single IP) or project (SoC, large algorithm, multi-block accelerator).
  Use this skill before any new module or system starts; after decisions are
  signed off, hand over to hardware-rtl-design.
---

# Hardware Design Planning (interrogate the brief to the end)

Writing RTL first and later discovering the partitioning, interface, or timing
was wrong is the most expensive rework in hardware. This skill puts the
**alignment conversation** up front at the right abstraction level:

- **Single block**? Press hard on interface, semantics, performance, and
  failure modes, and pin decisions down in 3 files.
- **Project**? **Ask partitioning first** (subsystems, top-level interconnect,
  clocks, memory map, milestones), then recurse the block flow into each
  subsystem. Decisions captured in a multi-file tree.

**This skill applies to any hardware design** — digital datapath, control FSM,
mixed-signal interface, clocking subsystem, DFT/BIST, PMU, RF, ML accelerator,
protocol engine, SerDes phy … all covered. The exemplars in `references/`
only demonstrate a few common shapes; when the design is fundamentally
different, the Q&A looks different too. The discipline of this skill is the
**rigor of the Q&A**, not a fixed set of questions.

## MUST gate (before writing any RTL)

Any new module, IP, subsystem, or SoC **must** go through this skill and pass
`plan-check` before starting RTL. This is the first stage of `/lp-front`, and
failure halts; other `/lp-*` stage commands do not enforce the gate to allow
fast iteration, **but** that only spares you the repeated check, not the skill
itself — at kickoff you still must run it once.

Skipping this step is the **most expensive mistake** in this stack: the cost
of a wrong partition or interface decision scales with how much RTL has
already been written on top of it. 30 minutes of Q&A vs N days of rewriting
— which one to pick is not up for discussion.

**Exceptions** (do not trigger this skill): modifications within an existing
spec — bug fix, refactoring, adding a bit to an already spec'd CSR map,
tweaking FSM state encoding, filling a missing default, renaming internal
signals, cleaning up comments. These only need
`hardware-design-discipline`.

**Not within the exceptions**: touching interfaces, touching module
boundaries, touching clock/reset structure, touching the address map, or any
change that invalidates the existing `docs/spec.md` — these count as new
design and must go through this skill first and pass `plan-check`.

## Core principles (apply to both scopes)

- **Do not silently guess** — if you do not know whether the user wants a
  2-FF or a handshake, AXI or APB, **ask**; do not decide for them.
- **Do not ask open-ended questions** — frame every ambiguity as a
  **multiple-choice**: options + ★ recommendation + one-line rationale.
  You must recommend one, and you must explain why.
- **"Other" escape hatch** — in the brainstorm round **every question must**
  carry `Other — <free text>`; in the implementation round only add it when
  3 options cannot cover ≥80% of answers.
- **Ask in batches** — 3–5 questions per round, not one at a time.
- **Land decisions immediately** — after each round, append to the
  corresponding document; the schema is decided by the design.

For the full elaboration and example format, see `references/principles.md`.

## Brainstorm round (before any decision Q&A)

The job of the brainstorm is to **map out the design space** — what kind of
hardware is this, what does it interface with, what are the real risks and
constraints — before converging on concrete implementation options. Without
the brainstorm, the default is to regress to "ask questions like for an SPI
master", which produces bad results for clocking subsystems, BIST
controllers, mixed-signal interfaces, and so on.

6 categories, in two batches of 3 questions each (every question carries
`Other`):

1. **Design nature** — datapath / control / mixed / clocking / analog
   interface / DFT / power management / RF / Other
2. **Host context** — CPU bus / standalone streaming / standalone control /
   chip-to-chip / network / no host / Other
3. **Primary risk** — Fmax / area / power / verification coverage /
   numerical correctness / signal integrity / interop / Other
4. **Hard constraints** — platform / latency / area / power / interop spec /
   schedule / security posture / Other
5. **Alternative directions** — agent proposes 2–4 alternatives, each with a
   verdict slot (select / reject / defer / unknown)
6. **Explicitly out of scope** — agent proposes 2–4 candidate OOS items, user
   picks and adds

For full option enumeration, the form of `docs/brainstorm.md` output (soft,
not gate-enforced), and the mechanism of "how brainstorm answers reorder the
subsequent Q&A", see `references/brainstorm-round.md`. Full exemplar in
`dialogue-brainstorm.md` (deliberately picked a non-CPU-attached design).

**Once Primary risk (Q3) + Hard constraints (Q4) are answered**, see
`references/target-driven.md` for: how to rank one primary target (timing /
area / power) with the others as constraints, what's worth doing per target,
common over-optimization traps (don't pipeline everything, don't chase 1 % at
the cost of latency / verification), and a stage-cost map so the cheapest fix
gets tried first.

## Two scopes — pick after brainstorm, before any implementation Q&A

| Scope | What the brief implies | Output |
|-------|------------------------|--------|
| **Block** | A single IP / peripheral / accelerator / bridge / FIFO / filter. ≤1 algorithm, ≤1 host bus interface, no internal memory map between blocks. | `docs/spec.md`, `docs/uarch.md`, `docs/plan.md` |
| **Project** | SoC, multi-block algorithm, CPU + peripherals, ≥3 internal subsystems, a top-level memory map spanning subsystems, multiple clock domains driving different subsystems, or explicit phased delivery. | `docs/arch.md`, `docs/integration_plan.md`, `docs/milestones.md`, plus `docs/subsystems/<name>/{spec,uarch,plan}.md` for each partition unit |

If it is not clear, **ask scope first** as Round 0:

```
0. Project scope:
   A) Single block — one IP, ≤~1k LoC, no internal partitioning needed  ★ if
      the brief really is just one block
   B) Subsystem — 2–5 tightly coupled blocks, implementing one algorithm or
      function  → project scope
   C) Full SoC / large algorithm — ≥3 subsystems, cross-subsystem memory
      map, possibly multi-clock, possibly phased delivery  ★ if the brief is
      that wide  → project scope
   D) Other — <describe in plain words what your design is>
      For cases that do not cleanly land in block/subsystem/SoC; the agent
      uses your free text to pick the closest of block or project scope, and
      explains the choice.

Pick one?
```

Wrong scope is not easy to recover cheaply: a design that is actually an SoC
started in block scope produces a shallow, flat, oversized spec.md; a single
block started in project scope is pure overhead.

## Block-scope workflow

Use when scope = block, with 3 documents under `docs/`. High-level steps:
**read brief → classify ambiguities (the generic 6 categories + extensions
by block shape) → frame every ambiguity as a multiple-choice → 3–5 questions
per batch → land decisions live into spec.md → move to uarch.md
(decomposition / datapath / control / FSM / pipeline / memory / file list)
→ plan.md as checkboxes**.

**Generic 6 categories of ambiguity** (apply to any block — do not start the
spec without covering all of them):

- Interface and protocol semantics (handshake, backpressure, error response)
- Clocks (count, source, asynchronous relationships, gating)
- Reset (sync vs async, polarity, per-domain scope)
- Performance targets (Fmax, throughput, latency, jitter)
- Failure modes (overflow, underflow, illegal input, timeout, recovery)
- Configurability (parameter vs hardcoded, legal ranges)

For the ambiguity check lists by block shape (CSR-mapped peripheral /
streaming / bridge / compute / CDC / memory controller) and the full 7-step
flow, see `references/block-workflow.md`.

## Project-scope workflow

Use when scope = project. 4 tiers: **Tier-0 architecture → Tier-1 per
subsystem (recurse block flow) → integration plan → milestones**.

### Tier-0: architecture Q&A (mandatory first round)

This asks about **partitioning**, not implementation. Always applies 4
categories: **Partition, clock plan, reset plan, platform target**. Only ask
the following when brainstorm "Host context" / "Design nature" answers
indicate they apply: **top-level interconnect / fabric, memory map,
interrupt / event routing, power / security domains**. Skip the category if
it is not relevant — do not force a clocking subsystem to invent a memory
map.

`docs/arch.md` requires a mandatory partition table — the heading may be
`## Subsystems`, `## Subsystem inventory`, `## Components`,
`## Pipeline stages`, `## Units`, `## Channels`, `## Blocks`, `## Modules`
(use whichever word fits the design most naturally). The first column = the
partition unit name, and it must be a valid directory name
(`[a-zA-Z][a-zA-Z0-9_-]*`), because plan-check expects
`docs/subsystems/<name>/` — the on-disk directory is always `subsystems/`,
regardless of which alias the heading uses (single source of truth for
layout).

### Tier-1: per-partition-unit Q&A (recurse the block flow)

For **every** name in the arch.md partition table, run the block-scope flow
above, producing `docs/subsystems/<name>/{spec,uarch,plan}.md`.

**Tier-1 references arch.md decisions, it does not redecide them** — clock
domain, reset source, address range, bus interface type, IRQ destination,
all are looked up in arch.md. Redeciding in Tier-1 is the **#1 inconsistency
bug**. If a unit genuinely needs to override an arch.md decision, **go back
to Tier-0 and update arch.md**, do not silently diverge.

For the full Tier-0 chapter list, the 5 categories of content in
integration_plan.md (cross-subsystem interfaces / top-level CDC / CSR map /
interrupt aggregation / top-level scenarios), and the P0/P1/Pn template of
milestones.md, see `references/project-workflow.md`. Exemplar:
`dialogue-soc-mldsa.md`.

## Ambiguities that cannot be skipped (apply to both scopes)

These will bite in silicon. If the brief did not say, **ask before writing
the spec**:

- **Reset polarity and deassert timing** — async/sync, active level, per
  domain.
- **CDC for any multi-clock signal** — even a 1-bit crossing requires a
  synchronizer choice. Do not trust "it is just one bit, does not matter".
- **Backpressure per interface** — when ready=0, who holds; when valid=0,
  what is defined.
- **Error response per interface** — SLVERR/DECERR, drop-and-set-status,
  block-and-flag — pick one per error class.
- **Overflow / underflow for every storage element** — FIFO full, counter
  wrap, state machine illegal-state recovery.
- **Interrupt semantics** — level vs edge, sticky vs auto-clear, mask vs
  enable, per-source vs aggregated.

## Per-module test allocation

When `uarch.md` (block or per subsystem) names submodules, **assign a
verification obligation to every one**. Skipping is not allowed —
allocation is the agent's public ledger, proving nothing was missed in the
decomposition.

This only does **allocation** — pin down the WHAT; HOW is handed to
`hardware-verification`. 3 categories of obligation; one module may carry
several:

- **reference-model** — outputs are independently computable (CRC, AES, FIR,
  NTT, compression, framer, scrambler, ECC, deterministic protocol
  translation). Name the golden source.
- **property/invariant** — timing / protocol / state rules (FIFO, arbiter,
  FSM, cache controller, protocol bridge, CDC wrapper, control-plane
  logic). Spell out the invariant as a one-line headline.
- **integration** — no meaningful standalone state, transform, arbitration,
  rule, or failure mode. **Must name the top-level test or coverage point
  that exercises it**; just writing "skip" is not allowed. Pure mux counts;
  a register slice with valid/ready **does not**.

Record in the File list of `uarch.md`:

| path | role | test | artifact |
|------|------|------|----------|
| rtl/ntt_core.sv    | NTT butterfly | reference-model                       | tools/ntt_ref.py (numpy, FIPS 204 Algo 41) |
| rtl/crc_step.sv    | CRC LFSR step | reference-model + property/invariant  | python crc32 step + FSM-legality |
| rtl/async_fifo.sv  | CDC FIFO      | property/invariant                    | ordering, no-loss, full/empty timing, Gray safety |
| rtl/axil_decode.sv | addr decode   | integration                           | covered by tb/top_smoke_tb.sv: all CSR addresses |

For project scope, integration_plan.md adds a parallel allocation at the
**top level** — the top-level scenario is the "top test" that some
subsystem's integration-bucket module points to.

## TB architecture planning (SystemVerilog)

For SystemVerilog projects, decide TB architecture-level choices in the same
planning round: cocotb vs UVM vs pure SV, interface/modport boundaries,
clocking-block boundaries (what the TB drives, what it samples), where
reference-model comparison vs property assertion sits in the TB hierarchy.
For project scope, also decide whether each subsystem has its own
unit-level harness or only participates via a top-level integration TB.
Concrete assertions, coverage points, stimulus constraints, randomization
knobs, seed strategy belong to `hardware-verification`, **not** here.

## Outputs

**Block scope** — `docs/{spec,uarch,plan}.md`.

**Project scope** — `docs/{arch,integration_plan,milestones}.md` +
`docs/subsystems/<name>/{spec,uarch,plan}.md` (one set for each name in the
arch partition table).

For the full file tree, references index, and glob caveats, see
`references/output-schema.md`.

## Gate

The `plan-check` flow stage auto-detects scope:

- `docs/arch.md` does not exist → block scope; validates the 3 block
  documents.
- `docs/arch.md` exists → project scope; validates the 3 top-level
  documents + the three-file set `docs/subsystems/<name>/{spec,uarch,plan}.md`
  for each name in the arch.md partition table. When arch.md itself fails
  (missing / trivial / placeholder), plan-check short-circuits and only
  reports the arch failure.

It checks: file existence, non-trivial content, no exemplar placeholder
residue, at least one checkbox per plan.md. It does **not** validate
section names, prose content, or domain semantics — content quality is the
agent's job, not the gate's. Fake rigor (filling in a table that was not
thought through, just to pass schema) is worse than no schema.

**The one narrow enumeration exception**: under project scope, arch.md must
contain a partition heading (one of the 8 aliases like `## Subsystems`),
followed by a markdown table whose first column is a valid directory name
(`^[a-zA-Z][a-zA-Z0-9_-]*$`) and unique. The rest is up to you.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/flow/logicpilot.py" plan-check --config flow.toml
```

`/lp-front` runs it first and halts on failure.

## Definition of done (MUST gate)

Before handing over to `hardware-rtl-design`, **all** of the following
**must** hold:

- [ ] **User has explicitly accepted the decisions** — block scope:
      `docs/spec.md`; project scope: `docs/arch.md` + every
      `docs/subsystems/<name>/spec.md`. "Looks OK" does not count as
      acceptance; an explicit "confirm" signal is required.
- [ ] **No "cannot-skip ambiguity" left blank** — reset polarity, CDC
      choice, backpressure semantics, error response, overflow / underflow,
      interrupt semantics — all six categories answered.
- [ ] **Every `plan.md` has at least one `- [ ]` checkbox** — an empty plan
      equals no plan.
- [ ] **(project scope only)** every name in the arch.md partition table has
      the full three-file set `docs/subsystems/<name>/{spec,uarch,plan}.md`;
      `integration_plan.md` and `milestones.md` are also signed off.
- [ ] **`plan-check` has actually been run and returned `status: pass`** —
      "should pass" does not count; run it, read the JSON, confirm.

If any item does not hold, it is **not done**. Say which gate is open, fix
it, and **do not** jump to writing RTL — the cost of a planning gate that
leaked = rewriting all affected RTL.
