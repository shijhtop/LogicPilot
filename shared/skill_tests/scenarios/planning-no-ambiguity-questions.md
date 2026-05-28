---
target_skill: hardware-design-planning
scenario: planning-no-ambiguity-questions
title: User gives a thin brief and asks for spec.md immediately
guards:
  - "Do not silently guess"
  - "Do not ask open-ended questions"
  - "multiple-choice"
  - "★ recommendation"
  - "Ambiguities that cannot be skipped"
gate_text:
  - "MUST gate"
  - "Definition of done (MUST gate)"
---

## Scenario prompt

> Write me a `docs/spec.md` for an SPI master IP. I want it to be reusable.

(The brief is intentionally vague: no clock spec, no CSR map, no IRQ
semantics, no FIFO depth, no error-response policy.)

## Baseline failure modes

- Writes a spec.md filled with picked-from-thin-air defaults: 8-bit data,
  mode 0, 1 MHz max, 4-deep FIFO, etc.
- Frames ambiguities as open-ended questions ("what should the FIFO
  depth be?") instead of multiple-choice with a recommendation.
- Does not ask about: reset polarity, CDC choice (if SPI clock is async
  to host), backpressure on the host bus interface, error response (CRC
  mismatch / overrun), CSR layout, IRQ semantics.
- Marks the spec "done" without user sign-off.
- Skips the "不能跳过的歧义" six-item checklist entirely.

## Expected guarded behaviors

- Refuses to silently pick defaults — asks the user instead.
- Frames every ambiguity as a multiple-choice (3–4 options, one ★
  recommendation with a one-line reason), per the 核心原则.
- Batches 3–5 questions per round, not one at a time.
- Hits the "不能跳过的歧义" six categories: reset polarity, multi-clock
  CDC, backpressure, error response, overflow/underflow, interrupt
  semantics.
- Records decisions in `docs/spec.md` as the user answers, not all at
  the end.
- Does not declare planning done until all five Definition-of-done MUST
  items are satisfied (including `plan-check` returning `status: pass`).

## Why this scenario exists

The thin brief is the most common scenario in practice. The skill exists
specifically to convert "write me a spec" into "let me ask you 12
multiple-choice questions whose answers become your spec." If the agent
falls back to filling in defaults, the planning gate has failed silently
and the rewrite cost is paid later.
