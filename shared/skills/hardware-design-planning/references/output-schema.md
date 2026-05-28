# Outputs and Project Layout

SKILL.md gives a 1-line summary; this file gives the full file inventory +
recommended directory structure + glob caveats.

## Block scope — 3 files under `docs/`

- `docs/spec.md` — alignment record (interfaces, protocol, performance, failure modes)
- `docs/uarch.md` — microarchitecture + File list with test assignments
- `docs/plan.md` — execution checkbox

## Project scope — top-level tree under `docs/`

- `docs/arch.md` — Tier-0 architecture (mandatory partition table: the heading
  may be one of `## Subsystems`, `## Subsystem inventory`, `## Components`,
  `## Pipeline stages`, `## Units`, `## Channels`, `## Blocks`,
  `## Modules`)
- `docs/integration_plan.md` — cross-subsystem contracts + top-level test scenarios
- `docs/milestones.md` — phased delivery
- `docs/subsystems/<name>/spec.md` — alignment record for each subsystem
- `docs/subsystems/<name>/uarch.md` — microarchitecture + File list for each subsystem
- `docs/subsystems/<name>/plan.md` — execution checkbox for each subsystem

## `references/` index

- **Brainstorm exemplar** (any scope, deliberately non-bus design):
  `dialogue-brainstorm.md` (clocking subsystem)
- **Block-scope exemplar** (CPU-attached / streaming / bridge / CDC / pure compute
  shape): `dialogue-peripheral-spi.md`, `dialogue-streaming-fir.md`,
  `dialogue-bridge-axil-apb.md`, `dialogue-async-fifo.md`,
  `dialogue-crc-engine.md`
- **Project-scope exemplar** (SoC / large algorithm): `dialogue-soc-mldsa.md`

These are **exemplars, not templates** — use them to learn the style, then ask
the questions raised by **your own** design brief. Don't copy the structure;
copy the discipline.

## Recommended project layout

### Block

```
my_block/
  flow.toml
  docs/              # spec.md, uarch.md, plan.md
  rtl/
  tb/
  constraints/
  build/
```

### Project

```
my_soc/
  flow.toml
  docs/
    arch.md
    integration_plan.md
    milestones.md
    subsystems/
      crypto_core/   # spec.md, uarch.md, plan.md
      csr_block/     # spec.md, uarch.md, plan.md
      bus_fabric/    # spec.md, uarch.md, plan.md
  rtl/
    crypto_core/...
    csr_block/...
    bus_fabric/...
    top/...
  tb/
    crypto_core/     # subsystem unit TB
    top/             # top-level integration TB (from integration_plan.md)
  constraints/
  build/
```

## glob caveats

If you use subfolders under `rtl/`, `flow.toml` must use a **recursive glob**
(`rtl/**/*.v`) — a non-recursive glob will **silently miss** files in subfolders.
plan-check passes, lint passes, but audit runs against an empty file set — this
kind of silent miss is one of the longest-to-discover bugs.
