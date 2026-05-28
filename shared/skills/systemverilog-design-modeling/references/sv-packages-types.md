# SystemVerilog packages, declarations, and types

## Namespace policy

- Put shared `typedef`, enum, struct, constants, parameters, and reusable helper
  functions in named packages.
- Compile packages before modules/interfaces that import or reference them.
- Avoid declaring shared objects in `$unit`; separate compilation can make them
  disappear or change meaning.
- Use package-qualified names for public APIs when clarity matters:
  `types_pkg::cmd_t`.
- Use wildcard imports only in small, controlled namespaces.

## Compile-order policy

Use `src_ordered` when package/interface order matters:

```toml
[project]
src_ordered = [
  "rtl/pkg/types_pkg.sv",
  "rtl/if/*.sv",
  "rtl/**/*.sv"
]
```

## Type policy

- `logic` is the 4-state single-driver variable type. Use it in `always_ff`
  / `always_comb` / `assign` interchangeably. More than one driver is a
  **compile-time error** — the tool catches the bug that with `reg` only
  showed up in simulation. **Default RTL type.**
- `wire` is reserved for true multi-driver resolved nets (tri-state buses,
  `assign` bus merging). Don't use it for normal single-driver signals.
- `reg` has no independent purpose in new SV-native code — prefer
  `logic`. Keep `reg` only when sharing files with pure Verilog-2001
  flows that haven't migrated.
- Use `typedef enum logic [N-1:0]` for FSM states and opcodes.
- **packed** `struct` / array is bit-contiguous: usable as one vector in
  ports, wires, `assign`, arithmetic. `$bits(s)` equals the sum of member
  widths. Packed struct can be a port type as long as both sides `typedef`
  from the same package.
- **unpacked** `struct` / array is separately-stored (memory-like) — cannot
  be treated as a vector; must access element-by-element.
- Declare signedness explicitly where arithmetic matters.
- Use static casts for intentional width / signedness conversion.

## 2-state vs 4-state

2-state types can improve simulation speed or model abstract data, but in RTL
they can hide X/Z behavior and reset issues. Use them only with a stated reason.
