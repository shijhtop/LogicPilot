# Constrained random and functional coverage

## Randomization rules

- Randomize what creates coverage value: configuration, packet shape, opcode,
  address, data pattern, stalls, errors, reset timing, and boundary cases.
- **Check every `randomize()` return value** — either
  `if (!obj.randomize()) $fatal("randomize failed");` or the concise
  immediate-assertion form `assert(obj.randomize());`. A bare
  `obj.randomize();` is an implicit void-cast that silently hides
  constraint failures.
- Log seed, test name, relevant plusargs, and configuration.
- Prefer unsigned random fields unless negative values are meaningful.
- Use inline constraints for test-local intent; use named constraint blocks for
  reusable policy.
- Use `solve ... before` only to intentionally shape probability.

## Common pitfalls

- A constraint can be legal but make important scenarios nearly impossible.
- Signed `byte`/`int` fields can produce negative values unexpectedly.
- Cross coverage can explode combinatorially; define bins and ignore impossible
  combinations.
- `randc` can be expensive for large domains.

## Coverage rules

- Coverage points should map to the verification plan.
- Sample after the transaction is accepted/observed.
- Use bins for semantic categories, not every raw value by default.
- Use crosses only when the combination matters.
- Use `illegal_bins` for scenarios that must never occur.
- Coverage from failing tests should not be merged into closure data.
- **`cover property` vs `assert property`**: a cover **passes** when the
  sequence is observed (positive evidence the scenario hit); an assert
  **fails** when the property is violated. Use cover for hard-to-hit
  corner cases (back-to-back full + write, single-cycle req-ack
  handshake) to prove coverage closure, not just constraint-driven hits.

## Closure loop

Run random tests with logged seeds, inspect coverage holes, adjust constraints or
add directed tests, rerun, then document unreachable or waived coverage.
