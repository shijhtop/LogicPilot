# Interfaces, clocking blocks, and race-aware TB timing

## Interfaces

Use an interface to collect protocol signals and shared tasks/checkers. Use
modports to define what each side may drive or sample. Do not let an interface
become a dumping ground for unrelated testbench behavior.

## Clocking blocks

Clocking blocks define when the testbench drives and samples relative to a clock.
They prevent races where the DUT and TB access the same signal in the same time
slot with ambiguous ordering.

Use them for synchronous protocol drivers and monitors, especially when the TB
drives exactly on the clock edge.

## Virtual interfaces

Class-based components cannot directly instantiate hardware interfaces. Pass a
virtual interface handle through configuration or constructor wiring. Keep the
component generic and bind it to a physical interface at the top testbench.

## Practical rules

- Drivers drive through the clocking block.
- Monitors sample through the clocking block or after DUT update.
- Avoid `#0` race fixes.
- Keep reset sequencing explicit and edge-aligned.
- Document clocking skew when it matters.
- **Type DUT-boundary signals as `logic` (4-state)** — never `bit` — so
  X-propagation from uninitialized DUT state remains visible. TB-internal
  counters, sequence IDs, scoreboard storage, and reference-model state
  may use `bit` (2-state) for clarity; the ~2× sim speedup is secondary
  to keeping X visible at the boundary.
- **Synchronizer-chain testbenches** should drive randomized 0 / 1 through
  potentially-metastable flops, not X. X-propagation through synchronizers
  produces X-pessimism that masks real CDC bugs; randomized 0 / 1 exposes
  both metastability-tolerant and metastability-sensitive downstream logic.
