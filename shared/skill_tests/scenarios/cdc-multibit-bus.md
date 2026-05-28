---
target_skill: hardware-cdc
scenario: cdc-multibit-bus
title: Multi-bit bus framed as "small enough to skip Gray-coding"
guards:
  - "Multi-bit bus through **parallel** 2-FF chains"
  - "Gray-coded"
  - "async FIFO"
  - "set_clock_groups -asynchronous"
gate_text:
  - "When this skill is mandatory (MUST gate)"
  - "Definition of done (MUST gate)"
  - "crossing inventory"
---

## Scenario prompt

> I have a 16-bit counter in a 100 MHz clock domain that needs to be read
> from a 50 MHz domain. Just put a 2-flop synchronizer on each bit — it's
> only 16 bits, the metastability window is small, and the counter only
> increments by 1 each cycle so the bits don't change much. Can you write
> the RTL?

## Baseline failure modes (what an unguarded agent typically does)

- Accepts the framing and writes 16 parallel 2-FF chains.
- Adds a comment like "synchronized for CDC safety" without flagging that
  parallel 2-FF on a bus is the wrong pattern entirely.
- Skips mentioning Gray coding, async FIFO, or req/ack-with-held-data.
- Does not produce a crossing inventory.
- Declares the work done from "code compiles."

The "only increments by 1" framing is a classic trap: even small
increments make multiple bits flip on carry boundaries (e.g. 0x0FFF →
0x1000), so parallel 2-FF can still capture an illegal intermediate value.

## Expected guarded behaviors (with hardware-cdc loaded)

- Refuses the user's framing in writing: parallel 2-FF on a multi-bit bus
  is unsafe regardless of bit width or expected change rate.
- Names the correct patterns: async FIFO with Gray-coded pointers (if the
  reader needs every value), Gray-coded counter (if the reader only needs
  a monotonic snapshot), or req/ack with held data (if event-driven).
- Produces a crossing inventory listing the 16-bit bus as a single
  multi-bit crossing, with the chosen pattern and verdict.
- Reminds the user to declare `set_clock_groups -asynchronous` to STA so
  the tool doesn't try to close the async path.
- Refuses to declare the work done until the inventory is complete and
  every crossing has a verdict (per Definition of done).

## Why this scenario exists

This is the load-bearing CDC failure mode: an agent that knows the words
"synchronizer" and "2-FF" but doesn't know they form a *family* of
patterns that apply differently by crossing kind. The user's framing
sounds reasonable; the skill must override it.
