# Core principles (apply to both scopes)

SKILL.md lists the principle names; this file expands the "why" and "how".

## Don't silently guess

When you don't know whether the user wants a 2-FF or handshake synchronizer, AXI or APB, single-clock or multi-clock — **don't decide for them**, ask. The cost of guessing on the engineer's behalf is: you only discover the interface or timing assumption was wrong after the RTL is written, and the whole block gets reworked. This is the only failure mode to avoid during the planning stage — everything else is detail.

## Don't ask open-ended questions

A question like "what should the reset strategy be" effectively asks the user to understand the hardware themselves. Frame every ambiguity as a **multiple-choice** question: options + recommendation + one-line rationale.

**Question format**:

```
<topic>:
  A) <option> — <one-line rationale>  ★ recommended
  B) <option> — <one-line rationale>
  C) <option> — <one-line rationale (if relevant)>
  Which one?
```

You must recommend one every time, and you must explain why you recommend it. If 4 options all look equally reasonable, it means you haven't thought it through — converge before asking. Pushing the engineering decision back onto the user is the biggest failure mode in this skill.

## "Other" escape hatch

Preset options cover the **typical** design space, but they can't cover every reasonable intent.

- In the **brainstorm round** (whose goal is to map out the design space — see
  `brainstorm-round.md`), **every question must** end with an `Other — <free text>` option, so the user can describe a direction you didn't anticipate.
- In the **implementation round** (whose goal is to pick among common engineering options), only add `Other` when 3 options can't cover ≥80% of reasonable answers. Don't sprinkle it everywhere — it reopens decisions that should already be closed.

## Batch the questions

3–5 questions per round, don't ask only one at a time. The user works through the list, you take the answers and move to the next batch. Asking one question at a time stretches the conversation past 20+ rounds, and the user gives up halfway through answering.

## Pin decisions down immediately

After each round of answers → append to the corresponding document in whatever structure the design needs. There is no fixed schema — a peripheral naturally grows a CSR table, an FFT naturally grows a fixed-point precision section, a bridge naturally grows a transaction mapping table. The schema is decided by the design; don't pre-fill a template.
