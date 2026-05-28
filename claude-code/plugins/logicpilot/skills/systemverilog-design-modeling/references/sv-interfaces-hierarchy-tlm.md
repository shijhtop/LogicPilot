# SystemVerilog hierarchy, interfaces, and TLM boundary

## Hierarchy

- Prefer named parameter overrides and `.name` / `.*` implicit port
  connections.
- Avoid `defparam`.
- **`.*` semantics**: the sub-module's port name AND width must match the
  upper net exactly — mismatch is a **compile-time error**, not a warning.
  Unconnected ports must be written explicitly as `.port_name()`.
  Width-slicing must be explicit as `.port(bus[hi:lo])`. Do not use `.*`
  on gate-level netlists (mass same-named `a` / `b` / `y` / `q` will get
  shorted).
- Use `generate` for structural replication; keep generated instance names
  predictable enough for constraints / debug.

## Interfaces

Interfaces are useful when a signal bundle appears repeatedly.

- Define `modport`s for each role: producer / consumer, master / slave,
  DUT / TB.
- Keep synthesizable interface contents simple and supported by the target
  tool.
- Interface tasks / functions used by RTL should be `automatic`.

## Clocking blocks

A `clocking` block binds a group of signals to one clock event plus an
input skew (default `1step` — samples Preponed) and an output skew
(default 0). `##N` inside the block is equivalent to
`repeat(N) @(default_clocking)`. TB driving / sampling through a clocking
block is automatically aligned to the clock edge without race against RTL.

- Allowed in `interface` / `module` / `program`. **Not** in synthesizable
  RTL — TB-only.
- Virtual interfaces belong in class-based TB components.

## Behavioral and transaction-level models

A transaction-level model hides signal-level handshakes behind tasks/functions or
method-like calls. It is useful for architecture and verification, but it is not
implementation RTL until refined into clocks, registers, handshakes, and storage.
