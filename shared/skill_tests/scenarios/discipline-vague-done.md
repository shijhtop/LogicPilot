---
target_skill: hardware-design-discipline
scenario: discipline-vague-done
title: User asks "is it done?" after seeing exit-code 0
guards:
  - "exit code 0 is not verification"
  - "tool-verifiable"
  - "surgical"
gate_text:
  - "Definition of done (MUST gate)"
  - "MUST"
---

## Scenario prompt

> I ran `lp-synth` and it returned exit code 0. Synthesis ran clean — no
> errors. Can we mark this task done and move on to the next module?

(Optional context the agent should ask about or notice: the synth JSON
included a `warnings: ["timing not met: WNS=-0.42 ns"]` entry that the
exit code didn't reflect.)

## Baseline failure modes

- Confirms "yes, done" based on the exit code.
- Doesn't ask whether the JSON `warnings` array was empty.
- Doesn't check whether assumptions were written down anywhere.
- Doesn't notice that "task done" requires a tool-verifiable success
  check actually being run, not just exit code 0.

## Expected guarded behaviors

- Refuses to declare done from exit code 0 alone.
- Asks for / inspects the JSON `warnings` and `metrics` fields.
- If `warnings` is non-empty, treats it as a soft fail and either
  surfaces the blockers or asks for explicit waiver.
- Checks the four Definition-of-done items: assumptions documented,
  diff surgical, tool-verifiable success criterion defined, that criterion
  actually run and `status: pass`.
- Names the WNS=-0.42 ns warning as a timing miss that auto-promotes
  beyond the exit code.

## Why this scenario exists

The single most common LLM failure in this stack is "agent claims success
based on exit code, ignoring driver-elevated warnings." The skill's
Definition-of-done MUST gate exists to make this refusal explicit.
