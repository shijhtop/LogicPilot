---
name: hardware-design-discipline
description: >-
  Cross-cutting habits for writing, editing, and reviewing RTL that prevent common LLM hardware mistakes: over-engineering, sprawling edits, silent assumptions, and unverified "make it work". Use whenever authoring or modifying HDL; applies on top of the domain skills, not instead of them.
---

# Hardware Design Discipline

Cross-cutting habits that catch the failure modes LLMs fall into when writing
hardware. These bias toward caution; for a trivial one-liner, use judgment.

## 1. Think before coding

Don't assume, don't hide confusion, surface trade-offs — *before* writing RTL.

- State the assumptions that shape the hardware: clock(s) and frequency, reset
  style, interface/handshake protocol, data widths, throughput/latency. If any
  is unstated, ask — guessing a reset strategy or an interface silently bakes in
  a rewrite.
- If multiple micro-architectures fit (e.g. pipelined vs iterative, one-hot vs
  binary FSM), present the trade-off; don't pick silently.
- If a simpler structure meets the spec, say so and push back.
- For anything non-trivial, plan first — hand off to `hardware-design-planning`.

## 2. Simplicity first — gates are real

Minimum logic that meets the spec. In hardware, speculative "flexibility" isn't
free abstraction — it synthesizes into area, power, and timing risk.

- No ports, parameters, `generate` blocks, or modes that weren't asked for.
- No FSM states, counters, or registers the function doesn't need.
- No "configurability" that turns into unused logic (it either wastes resources
  or gets optimized away — and then warns).
- No handling for cases the protocol/spec makes impossible.
- If a block is sprawling and could be half the logic, restructure it.

Ask: "would a senior RTL designer call this overbuilt?" If yes, simplify. See
`hardware-synthesizable-coding` for what the extra logic actually infers.

## 3. Surgical changes — RTL has side-effects

Touch only what the request needs; editing adjacent RTL can silently change
synthesis results.

- Don't "improve" neighboring logic, comments, or formatting.
- Don't re-time or restructure code that isn't broken — it can change area,
  Fmax, or inference (an innocent edit can introduce a latch).
- Match the existing coding style (blocking/nonblocking discipline, naming,
  reset convention) even if you'd do it differently — consistency is
  synthesizable correctness here.
- Remove only the signals/registers/instances *your* change orphaned; flag
  pre-existing dead logic, don't delete it unasked.
- Every changed line should trace to the request. After an edit, re-check the
  driver's `warnings` (latch / multi-driver) — a non-surgical edit shows up
  there.

## 4. Goal-driven execution — loop until verified

This is the plugin's core loop. Turn vague tasks into verifiable hardware goals
and iterate on the driver's `pass`/`fail`/`blocked` JSON.

- "Fix the bug" → write a self-checking testbench or assertion that *fails* on
  the bug, then change RTL until sim passes and `synth` is clean.
- "Add a feature" → add the coverage point / assertion first, then implement
  until it passes (see `hardware-verification`).
- "Refactor X" → confirm the testbench passes before and after; for structural
  refactors, an equivalence check.
- For multi-step work, state a brief plan with per-step verification:
  ```
  1. <step> → verify: lint clean, no latch warnings
  2. <step> → verify: self-checking sim passes
  3. <step> → verify: synth fits / timing met (with constraints)
  ```

Strong, tool-checkable success criteria let the agent loop on its own. "Make it
work" doesn't — exit codes aren't proof; read the report.

## Definition of done (MUST gate)

You MUST satisfy all four items below before declaring any RTL change done.
A failure to verify is a failure of the work itself, not paperwork:

- [ ] **Assumptions are written down** (in `docs/spec.md`, the PR description,
      or a checked-in note) — not held only in your head. The next reader
      must be able to reconstruct what you bet on.
- [ ] **Diff is surgical** — touches only what the request requires; no
      opportunistic refactors, restyling, or comment polishing in adjacent
      RTL. Every changed line traces to the request.
- [ ] **Success is defined as a tool-verifiable check** — a specific sim
      passing, lint warning count, synth timing slack, assertion firing, or
      coverage point. "Looks right" and "compiles" do not count.
- [ ] **That check was actually run, the JSON was read, and `status: pass`**
      — exit code 0 is not verification; flow stages can pass with
      `warnings` that hide real bugs.

If any item is not met, the change is not done. Say so and continue working
or surface the blocker — do not declare completion.
