---
target_skill: hardware-cdc
scenario: cdc-reset-deassert
title: Async reset shared across domains without per-domain sync deassert
guards:
  - "Reset deassertion is synchronized per domain"
  - "Assert async"
  - "deassert sync"
gate_text:
  - "Definition of done (MUST gate)"
  - "Reset deassertion is synchronized per domain"
---

## Scenario prompt

> I have two clock domains (clk_a at 200 MHz, clk_b at 33 MHz). Both use
> the same external active-low async reset pin `rst_n`. Each domain has
> its own always block with `always @(posedge clk_x or negedge rst_n)`.
> Looks correct, right? Both flops asynchronously reset off the same pin.

## Baseline failure modes

- Confirms "looks correct" and moves on.
- Notes "async reset is fine" without flagging the deassertion hazard.
- Misses that releasing `rst_n` is an asynchronous *event* relative to
  both clocks — so the two domains exit reset on different cycles, and
  registers depending on relative ordering see an illegal transient.
- Does not recommend per-domain reset synchronizers.

## Expected guarded behaviors

- Surfaces the RDC (reset-domain crossing) hazard: assertion can be
  asynchronous, but **deassertion must be synchronized per clock domain**
  (assert async, deassert sync — `Reset deassertion is synchronized per
  domain`).
- Recommends a reset synchronizer per domain (two FFs clocked by the
  destination clock, async-cleared by the source reset, fed by VCC).
- Lists `rst_n` deassertion as a reset-release crossing in the inventory.
- Refuses to declare the design done until the per-domain reset
  synchronizer is in place or the crossing is explicitly waived with a
  written reason.

## Why this scenario exists

RDC bugs survive both sim (zero-delay) and STA (single-domain). They
also "look correct" to a designer used to async resets. The skill must
catch the deassertion hazard by name.
