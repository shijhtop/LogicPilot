# Project-scope workflow

Use when scope = project. 4 tiers: Tier-0 architecture, Tier-1 per-subsystem
(recursive block flow), integration plan, milestones. SKILL.md gives the
outline; this file expands the required structure and pitfalls.

## Tier-0: architecture Q&A (mandatory first round)

The question is **partitioning**, not implementation. Some categories apply
to every project; others only when brainstorm answers indicate they apply.
**Skip the category if it's not relevant** — don't force a clocking subsystem
to invent a memory map, don't force a BIST controller to invent an interrupt
routing strategy.

### Always applies

1. **Partition** — what blocks/components/stages/units/channels exist, and
   what each owns. When the brief is ambiguous, offer 2–3 partitioning
   options. Each partition unit's name becomes its directory name.
2. **Clock plan** — number of global clocks, frequencies, asynchronous
   relationships, which domain each partition unit sits in.
3. **Reset plan** — single root vs per-domain, async / sync, polarity,
   release coordination.
4. **Platform target** — FPGA family (and part) or ASIC node. Drives BRAM
   vs distributed RAM choice, DSP inference, retiming budget.

### Conditionally applies — only ask when brainstorm answers indicate the category applies

5. **Top-level interconnect / fabric** — **if** the design has a CPU host
   or other standard interconnect (AXI4 / AXI4-Lite / APB / AHB / Wishbone
   / custom). Skip for standalone streaming, clocking, DFT, RF, and most
   analog interface designs.
6. **Memory map** — **if** the design exposes host-visible memory (CSRs,
   key/data buffers). Skip when there's no host.
7. **Interrupt / event routing** — **if** the design needs to report events
   to a host. Skip when there's nothing to report.
8. **Power / security domains** — **if** isolation boundaries, power
   gating, or secure / non-secure partitioning exist. Skip single-domain
   designs.

Use as many Q&A rounds as needed to cover applicable categories — don't
pad with irrelevant ones just to hit a count.

## Output: `docs/arch.md`

Required structure (loose — section names only, no prescribed table shape;
include only the sections brainstorm answers indicate are needed):

- **Project goal** (1–2 paragraphs on what the whole thing does)
- **Partition table** — **mandatory**. Heading may be any of:
  `## Subsystems`, `## Subsystem inventory`, `## Components`,
  `## Pipeline stages`, `## Units`, `## Channels`, `## Blocks`,
  `## Modules` — use whichever word best fits the design's natural
  partitioning vocabulary.
  First column = partition unit name; must be a legal directory name
  `[a-zA-Z][a-zA-Z0-9_-]*`, because plan-check creates / expects
  `docs/subsystems/<name>/` (the on-disk directory is always `subsystems/`,
  regardless of which heading alias the table uses — single source of
  truth for layout).
  Other columns are design-driven — typical set: role, clock domain,
  power domain, external interfaces.
- Clock plan (table or prose; mandatory if ≥2 clocks)
- Reset plan
- Platform target
- Top-level interconnect / fabric — *if applicable* (skip for non-bus
  designs)
- Memory map (table: address range → unit) — *if applicable*
- Interrupt routing — *if applicable*
- Power / security domains — *if applicable*
- **Partitioning rationale** — 1–2 paragraphs on **why this split and not
  another**. This is the design call that's most expensive to rework
  later.

## Tier-1: per-partition-unit Q&A (recursive block flow)

For **every** name in arch.md's partition table (whether the heading is
`## Subsystems`, `## Components`, `## Pipeline stages`, or something else),
run the 7 steps of `block-workflow.md` for that unit. Each produces:

```
docs/subsystems/<name>/spec.md
docs/subsystems/<name>/uarch.md
docs/subsystems/<name>/plan.md
```

The on-disk path is always `subsystems/<name>/`, even if the arch heading
used `Components` or `Pipeline stages` — single source of truth for layout.

A unit's spec.md **references arch.md's decisions** — it does not re-decide
them:

- Clock domain → arch.md
- Reset source → arch.md
- Address range → arch.md memory map (if applicable)
- Bus interface type → arch.md (if applicable)
- IRQ destination → arch.md interrupt routing (if applicable)

Re-deciding at Tier-1 is the **#1 inconsistency bug**. If a unit genuinely
needs to override an arch.md decision, that's a signal: go back to Tier-0
and update arch.md, don't silently diverge.

## Integration planning (after all Tier-1s are signed off)

Output → `docs/integration_plan.md`. Required content shape:

- **Cross-subsystem interfaces** — table: `from / to / protocol /
  handshake / width`. Every wire leaving one subsystem and entering
  another is named.
- **Top-level CDC inventory** — every cross-subsystem signal that crosses
  a clock boundary, plus the chosen synchronizer (2-FF / async FIFO /
  handshake) and source/destination domains. Intra-subsystem CDC stays
  in that subsystem's uarch.md.
- **Aggregated CSR map** — *if applicable* (the project has a CPU host
  or other host-visible address space): the actual top-level address map
  (union of each subsystem's CSR block), with the offset each subsystem
  occupies. Skip for projects without a host (clocking, DFT, RF,
  standalone control, most analog interface designs).
- **Aggregated interrupts / event aggregation** — *if applicable*: IRQ
  aggregation table from each subsystem to the host, or any outbound
  event contract (status pin, completion strobe, error flag). Skip when
  there's nothing to report to.
- **Top-level test scenarios** — always applies: end-to-end sequences
  spanning ≥2 partition units. Each scenario names which units it
  exercises and which invariants it confirms. The integration TB is
  built from these scenarios.

## Milestone planning

Output → `docs/milestones.md`. Required: **≥2 milestones**. Typical:

- **P0 — interface stub-out**: every subsystem's external interfaces are
  wired up, internals stubbed. Goal = the integration TB compiles and a
  smoke test runs through (no functional correctness yet).
- **P1 — critical path**: one end-to-end scenario from integration_plan.md
  runs on real RTL. Other subsystems may still be stubs. List which are
  real and which are stubs.
- **P2..Pn** — fill in remaining functionality, optimize, harden.

Every milestone has explicit, testable acceptance criteria, ideally bound
to a named scenario in integration_plan.md.

## Exemplar

`dialogue-soc-mldsa.md` — a project-scope example for an MLDSA-44 IP. It is
an **exemplar, not a template** — learn the style, don't copy the structure.
