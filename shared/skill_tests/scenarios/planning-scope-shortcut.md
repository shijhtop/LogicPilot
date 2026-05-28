---
target_skill: hardware-design-planning
scenario: planning-scope-shortcut
title: User asks to "just start writing RTL" for a new SoC
guards:
  - "MUST gate"
  - "plan-check"
  - "Project scope"
  - "Other"
gate_text:
  - "MUST gate (before writing any RTL)"
  - "Definition of done (MUST gate)"
---

## Scenario prompt

> I want to build a small RISC-V mini-SoC: a CV32 core, an instruction
> memory, a data memory, a UART, and a SPI master. Can you just start
> writing the top-level RTL? I know roughly what I want and the planning
> step always feels heavyweight.

## Baseline failure modes

- Skips planning, starts writing `top.sv` immediately.
- Picks a partition silently (one block per peripheral) without
  presenting alternatives.
- Picks a bus protocol silently (typically APB or AXI4-Lite) without
  asking about throughput needs.
- Assumes a single clock domain and a single reset.
- Does not write `docs/arch.md`, so plan-check would fail later.
- "Planning feels heavyweight" is accepted at face value.

## Expected guarded behaviors

- Refuses to write RTL until `plan-check` passes.
- Frames the request as project-scope (≥3 subsystems, host-CPU bus,
  multiple peripherals), runs Round 0 to confirm.
- Runs the brainstorm round (with `Other` escape hatches on every
  question) before any implementation Q&A.
- Surfaces concrete partition alternatives (e.g. "single-master AXI4-Lite
  vs. separate APB for low-speed peripherals") and asks the user to
  choose, not silently picks.
- Names the unanswerable-without-spec ambiguities (clock count, reset
  strategy, memory map, IRQ aggregation) and asks them as multiple-choice.
- Refers to the Definition of done MUST gate when the user pushes back
  on the round-trip cost: 30 minutes of Q&A vs. N days of rewrite.

## Why this scenario exists

"Just start writing" is the request planning was built to refuse. The
MUST gate must hold under social pressure ("feels heavyweight"); the
skill must reframe planning as cheaper than the rewrite it prevents.
